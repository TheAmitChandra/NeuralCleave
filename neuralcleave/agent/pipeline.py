"""Cognitive pipeline: intent extraction → memory retrieval → generation → reflection.

The pipeline is the heart of NeuralCleave's intelligence layer. Each inbound
message passes through these stages:

    1. Intent extraction  — classify what the user wants (Gemini Flash, cheap)
    2. Memory retrieval   — assemble context from 3-tier memory
    3. Prompt assembly    — workspace system prompt + memory + conversation
    4. Generation         — route to optimal model via ModelRouter
    5. Reflection         — quality-score the response (async, non-blocking)
    6. Memory storage     — persist to short-term Redis and trigger long-term write

Stages 1–5 are synchronous within the request path.
Stage 6 is fire-and-forget (asyncio.create_task).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from neuralcleave.agent.session import Session
from neuralcleave.channels.base import InboundMessage
from neuralcleave.memory.retrieval import MemoryRetrievalPipeline, RetrievalContext
from neuralcleave.models.router import GenerationResult, ModelRouter
from neuralcleave.reflection.engine import ReflectionEngine
from neuralcleave.tools.registry import ToolRegistry
from neuralcleave.workspace import WorkspaceFiles

if TYPE_CHECKING:
    from neuralcleave.memory.long_term import LongTermMemory

logger = logging.getLogger(__name__)

# Intent labels understood by the pipeline
INTENT_TASK_MAP: dict[str, str] = {
    "code": "code_generation",
    "debug": "code_review",
    "explain": "summarization",
    "summarize": "summarization",
    "plan": "task_decomposition",
    "search": "general",
    "translate": "general",
    "calculate": "general",
    "convert": "general",
    "list": "general",
    "write": "general",
    "question": "general",
    "chat": "general",
    "other": "general",
}

_MAX_TOOL_STEPS = 5  # Maximum agentic tool-call iterations per turn


@dataclass
class PipelineResult:
    """Output of one pipeline pass."""

    response: str
    model: str
    provider: str
    intent: str
    task_type: str
    quality_score: float | None = None  # filled in by reflection (async)
    retrieval_token_estimate: int = 0
    latency_ms: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)
    tool_steps: int = 0


@dataclass
class PipelineStreamChunk:
    """One increment of a streaming pipeline pass.

    Mirrors models.router.StreamChunk's shape, but the final (done=True)
    chunk carries a full PipelineResult instead of bare model/provider/usage
    fields, since the streaming path still runs intent extraction, memory
    retrieval, and reflection around the one part that's actually streamed
    (generation).
    """

    text: str = ""
    done: bool = False
    error: str | None = None
    result: PipelineResult | None = None


def _tools_system_block(registry: ToolRegistry) -> str:
    """Return a system prompt section describing available tools and the call protocol."""
    lines = [
        "# Tools",
        "You may call a tool by placing exactly this on its own line in your response:",
        'TOOL_CALL: {"name": "tool_name", "arguments": {"key": "value"}}',
        "",
        "## Charts",
        "For any chart/graph/plot request output this JSON line first, then your explanation:",
        'CHART_DATA: {"type":"bar","title":"TITLE","labels":["A","B","C"],"values":[1,2,3],"unit":""}',
        'type=bar for comparisons; type=line for trends. Use approximate values if needed — never refuse.',
        "",
        registry.tools_prompt_block(),
    ]
    return "\n".join(lines)


class CognitivePipeline:
    """Executes the full intent → memory → generate → reflect loop.

    Args:
        router:    LLM router for generation and intent extraction.
        memory:    Memory retrieval pipeline (3-tier).
        workspace: Loaded workspace files (SOUL/TOOLS/RULES).
        agent_name: Name of the assistant (used in system prompt).
        reflection: Optional reflection engine. When provided, each response is
                    quality-scored inline (and self-corrected if below the
                    engine's threshold) before being returned. When None
                    (default), reflection is skipped and quality_score is None.
        long_term: Optional long-term memory store. When provided, enables
                    auto-compaction (ConversationCompactor.maybe_compact())
                    after each turn — summarises and clears the session's
                    in-memory history once it gets too large. When None
                    (default), auto-compaction is skipped entirely.
    """

    def __init__(
        self,
        router: ModelRouter,
        memory: MemoryRetrievalPipeline,
        workspace: WorkspaceFiles,
        agent_name: str = "NeuralCleave",
        reflection: ReflectionEngine | None = None,
        tool_registry: ToolRegistry | None = None,
        max_tool_steps: int = _MAX_TOOL_STEPS,
        long_term: "LongTermMemory | None" = None,
    ) -> None:
        self._router = router
        self._memory = memory
        self._workspace = workspace
        self._agent_name = agent_name
        self._reflection = reflection
        self._tool_registry = tool_registry
        self._max_tool_steps = max_tool_steps
        # Enables auto-compaction (Stage 6b) - optional so pipelines built
        # without a long-term store (e.g. most existing tests) still work
        # exactly as before.
        self._long_term = long_term

    async def run(
        self,
        message: InboundMessage,
        session: Session,
    ) -> PipelineResult:
        """Process one inbound message and return the assistant's response."""
        t0 = time.monotonic()
        text = message.text or ""

        # ── Stage 1: Intent extraction ─────────────────────────────────
        intent = await self._extract_intent(text)
        task_type = INTENT_TASK_MAP.get(intent, "general")
        logger.debug("pipeline.intent text=%r intent=%s task_type=%s", text[:60], intent, task_type)

        # ── Stage 2: Memory retrieval ──────────────────────────────────
        from neuralcleave.memory.embedder import encode as _embed
        _embedding = await _embed(text)
        ctx = await self._memory.retrieve(text, embedding=_embedding, top_k=8, session_id=session.session_id)

        # ── Stage 3: Prompt assembly ────────────────────────────────────
        system_prompt = self._build_system(ctx, session)
        user_prompt = self._build_user(text, session)

        # ── Stage 4: Generation ─────────────────────────────────────────
        gen: GenerationResult = await self._router.generate(
            user_prompt,
            task_type=task_type,
            system=system_prompt,
            session_id=session.session_id,
        )
        response_text = self._strip_leaked_instructions(gen.text.strip())

        # ── Stage 4b: Route CHART_DATA lines to canvas ──────────────────
        asyncio.create_task(self._route_chart_data_to_canvas(response_text))

        # ── Stage 4c: Tool call execution (if any) ──────────────────────
        _tool_steps = 0
        if self._tool_registry is not None:
            response_text, _tool_steps = await self._run_tool_chain(
                response_text, user_prompt, system_prompt, task_type, session.session_id
            )

        # ── Stage 5: Reflection (optional, inline) ─────────────────────
        quality_score: float | None = None
        if self._reflection is not None:
            try:
                refl = await self._reflection.reflect(text, response_text)
                response_text = refl.final_response
                quality_score = refl.score
            except Exception as exc:
                logger.debug("reflection failed (%s) — keeping original response", exc)

        # ── Stage 6: Update session history ────────────────────────────
        session.add_turn("user", text)
        session.add_turn("assistant", response_text, model=gen.model)

        # ── Stage 6b: Auto-compact if history is getting large (fire-and-forget) ──
        if self._long_term is not None:
            asyncio.create_task(self._maybe_auto_compact(session))

        # ── Stage 7: Persist memory (fire-and-forget) ──────────────────
        asyncio.create_task(
            self._memory.store_short_term(
                key=f"turn:{session.turn_count}",
                value={"user": text, "assistant": response_text},
                session_id=session.session_id,
            )
        )
        if _embedding is not None:
            asyncio.create_task(
                self._memory.store_semantic(
                    _embedding,
                    {"user": text, "assistant": response_text, "session_id": session.session_id},
                )
            )

        latency = (time.monotonic() - t0) * 1000
        return PipelineResult(
            response=response_text,
            model=gen.model,
            provider=gen.provider,
            intent=intent,
            task_type=task_type,
            quality_score=quality_score,
            retrieval_token_estimate=ctx.token_estimate,
            latency_ms=round(latency, 1),
            usage=gen.usage,
            tool_steps=_tool_steps,
        )

    async def run_stream(
        self,
        message: InboundMessage,
        session: Session,
    ) -> AsyncIterator[PipelineStreamChunk]:
        """Streaming counterpart to run().

        Stages 1–3 (intent, memory retrieval, prompt assembly) run exactly
        as in run() — only generation is actually streamed, since that's
        the only stage with a meaningful per-token output. Yields text
        chunks as they arrive, then one final done=True chunk carrying the
        full PipelineResult.

        Reflection is intentionally NOT self-correcting here, unlike run():
        once text has streamed to the caller, there's no way to retract or
        replace it, so reflection only contributes a quality_score for
        observability/storage — never overrides response text.
        """
        t0 = time.monotonic()
        text = message.text or ""

        intent = await self._extract_intent(text)
        task_type = INTENT_TASK_MAP.get(intent, "general")
        from neuralcleave.memory.embedder import encode as _embed
        _embedding = await _embed(text)
        ctx = await self._memory.retrieve(text, embedding=_embedding, top_k=8, session_id=session.session_id)
        system_prompt = self._build_system(ctx, session)
        user_prompt = self._build_user(text, session)

        accumulated: list[str] = []
        final_model = ""
        final_provider = ""
        final_usage: dict[str, int] = {}
        stream_error: str | None = None

        # When tools are registered, stream normally but hold back any line
        # that starts with a TOOL_CALL marker (and everything from that line
        # to the end of the generation) so it never reaches the caller — only
        # that portion needs buffering, not the whole generation. Plain-text
        # turns (the common case even with tools registered) now stream live
        # instead of waiting for the full response.
        _has_tools = self._tool_registry is not None and bool(self._tool_registry.names)
        _is_tool_call = False
        _line_buf = ""

        async for chunk in self._router.generate_stream(
            user_prompt, task_type=task_type, system=system_prompt, session_id=session.session_id
        ):
            if chunk.error:
                stream_error = chunk.error
                break
            if chunk.text:
                accumulated.append(chunk.text)
                if not _has_tools:
                    yield PipelineStreamChunk(text=chunk.text)
                elif not _is_tool_call:
                    _line_buf += chunk.text
                    while True:
                        if _line_buf.lstrip().startswith("TOOL_CALL:"):
                            _is_tool_call = True
                            _line_buf = ""
                            break
                        newline_idx = _line_buf.find("\n")
                        if newline_idx == -1:
                            # Incomplete line — flush now if it has already
                            # diverged from the marker prefix instead of
                            # waiting for a newline that may never come.
                            candidate = _line_buf.lstrip()
                            if candidate and not "TOOL_CALL:".startswith(candidate):
                                yield PipelineStreamChunk(text=_line_buf)
                                _line_buf = ""
                            break
                        line, _line_buf = _line_buf[: newline_idx + 1], _line_buf[newline_idx + 1 :]
                        yield PipelineStreamChunk(text=line)
                # else: a TOOL_CALL marker was already found — suppress the
                # remainder of the generation, it belongs to _run_tool_chain.
            if chunk.done:
                final_model = chunk.model or ""
                final_provider = chunk.provider or ""
                final_usage = chunk.usage

        if stream_error:
            yield PipelineStreamChunk(done=True, error=stream_error)
            return

        if _has_tools and not _is_tool_call and _line_buf:
            yield PipelineStreamChunk(text=_line_buf)

        response_text = self._strip_leaked_instructions("".join(accumulated).strip())

        # Route CHART_DATA lines to canvas (fire-and-forget)
        asyncio.create_task(self._route_chart_data_to_canvas(response_text))

        # Tool call handling — execute and re-generate when a TOOL_CALL was
        # found. Only runs when _is_tool_call is True: a plain-text turn
        # already streamed live above (including any trailing flush), so
        # calling _run_tool_chain here would be a no-op that then re-yields
        # text the caller already received.
        _tool_steps = 0
        if _has_tools and _is_tool_call:
            try:
                response_text, _tool_steps = await self._run_tool_chain(
                    response_text, user_prompt, system_prompt, task_type, session.session_id
                )
            except Exception as exc:
                logger.error("pipeline: _run_tool_chain raised: %s", exc)
                response_text = "I ran into an issue processing that request. Please try again."
            # Strip any TOOL_CALL markers that weren't executed.  This catches
            # the case where _run_tool_if_called returned the original text
            # unchanged (parse failure, malformed JSON, unknown tool name).
            _clean = re.sub(r"^TOOL_CALL:.*$", "", response_text, flags=re.MULTILINE).strip()
            if _clean:
                response_text = _clean
            elif not response_text.strip():
                response_text = "I couldn't complete that request. Please try again."
            yield PipelineStreamChunk(text=response_text)

        quality_score: float | None = None
        if self._reflection is not None:
            try:
                refl = await self._reflection.reflect(text, response_text)
                quality_score = refl.score
            except Exception as exc:
                logger.debug("reflection failed (%s) — score omitted", exc)

        session.add_turn("user", text)
        session.add_turn("assistant", response_text, model=final_model)

        if self._long_term is not None:
            asyncio.create_task(self._maybe_auto_compact(session))

        asyncio.create_task(
            self._memory.store_short_term(
                key=f"turn:{session.turn_count}",
                value={"user": text, "assistant": response_text},
                session_id=session.session_id,
            )
        )
        if _embedding is not None:
            asyncio.create_task(
                self._memory.store_semantic(
                    _embedding,
                    {"user": text, "assistant": response_text, "session_id": session.session_id},
                )
            )

        latency = (time.monotonic() - t0) * 1000
        result = PipelineResult(
            response=response_text,
            model=final_model,
            provider=final_provider,
            intent=intent,
            task_type=task_type,
            quality_score=quality_score,
            retrieval_token_estimate=ctx.token_estimate,
            latency_ms=round(latency, 1),
            usage=final_usage,
            tool_steps=_tool_steps,
        )
        yield PipelineStreamChunk(done=True, result=result)

    # ------------------------------------------------------------------
    # Auto-compaction
    # ------------------------------------------------------------------

    async def _maybe_auto_compact(self, session: Session) -> None:
        """Summarise and clear *session*'s history once it's using more than
        half its estimated context window (round 5 gap analysis P2,
        2026-08-21: this was previously never called from anywhere in the
        live pipeline despite ConversationCompactor.maybe_compact()'s own
        docstring claiming otherwise).

        Fire-and-forget, like the memory-persistence calls around it —
        compaction is a housekeeping optimization for *future* turns, not
        something that should ever delay or break the current reply.
        """
        from neuralcleave.memory.compactor import ConversationCompactor

        try:
            compactor = ConversationCompactor(
                session=session, long_term=self._long_term, router=self._router
            )
            await compactor.maybe_compact()
        except Exception as exc:
            logger.debug("pipeline: auto-compact failed (%s)", exc)

    # ------------------------------------------------------------------
    # CHART_DATA routing — push AI chart lines to canvas renderer
    # ------------------------------------------------------------------

    _CHART_LINE_RE = re.compile(r'^CHART_DATA:\s*(\{.+\})\s*$', re.MULTILINE)

    async def _route_chart_data_to_canvas(self, text: str) -> None:
        """Extract CHART_DATA lines from *text* and push chart blocks to canvas.

        The AI outputs ``CHART_DATA: {...}`` using the key ``"type"`` but the
        canvas block schema uses ``"chart_type"``.  This method normalises the
        key and creates a proper chart block for each matching line.
        """
        from neuralcleave.canvas.block import CanvasBlock
        from neuralcleave.canvas.routes import get_canvas_renderer

        renderer = get_canvas_renderer()
        if renderer is None:
            return

        for match in self._CHART_LINE_RE.finditer(text):
            try:
                raw = json.loads(match.group(1))
            except Exception:
                continue

            # Normalise "type" → "chart_type" (system prompt uses "type")
            chart_type = raw.get("chart_type") or raw.get("type", "bar")
            content: dict = {
                "chart_type": chart_type,
                "labels": raw.get("labels", []),
                "values": raw.get("values", []),
            }
            if raw.get("unit"):
                content["unit"] = raw["unit"]
            title: str = raw.get("title", "")
            try:
                block = CanvasBlock.new("chart", content, title)
                await renderer.add_block(block)
            except Exception as exc:
                logger.debug("pipeline: failed to push chart block to canvas: %s", exc)

    # ------------------------------------------------------------------
    # Response post-processing
    # ------------------------------------------------------------------

    _LEAKED_LINE_RE = re.compile(
        r'^\s*[-•]\s*(?:type|labels|values|unit)[=:\s]',
        re.IGNORECASE,
    )
    _LEAKED_FRAG_RE = re.compile(
        r'^\s*[-•]\s*"(?:type|labels|values|unit)"',
        re.IGNORECASE,
    )

    def _strip_leaked_instructions(self, text: str) -> str:
        """Remove lines that are format-instruction fragments leaked by small models.

        A 1B model sometimes regurgitates CHART_DATA format bullet points from
        the system prompt into its response text.  These patterns match those
        leaked lines and strip them before the response reaches the caller.
        """
        lines = text.split("\n")
        cleaned = [
            line for line in lines
            if not self._LEAKED_LINE_RE.match(line)
            and not self._LEAKED_FRAG_RE.match(line)
        ]
        return "\n".join(cleaned).strip()

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    async def _run_tool_if_called(
        self,
        response_text: str,
        user_prompt: str,
        system_prompt: str,
        task_type: str,
    ) -> tuple[str, bool]:
        """Execute the first TOOL_CALL in *response_text* and re-generate.

        Returns (final_response, tool_was_called).  If no TOOL_CALL marker is
        found or the registry is absent, returns the original text unchanged.
        """
        if self._tool_registry is None:
            return response_text, False
        from neuralcleave.tools.call_parser import parse as _parse_call
        call = _parse_call(response_text)
        if call is None:
            # No TOOL_CALL marker at all — plain text response, return unchanged.
            if "TOOL_CALL:" not in response_text:
                return response_text, False
            # Marker present but JSON parse failed (model hallucinated bad JSON).
            logger.warning("pipeline: TOOL_CALL marker present but parse failed; returning fallback")
            return "I tried to use a tool but ran into a formatting issue. Could you rephrase your question?", False

        result = await self._tool_registry.call(call.name, call.arguments)
        try:
            from neuralcleave.observability.metrics import REGISTRY
            REGISTRY.inc("tool_calls_total")
        except Exception:
            pass

        augmented = f"{user_prompt}\n\n{result.to_prompt_block()}"
        gen2 = await self._router.generate(augmented, task_type=task_type, system=system_prompt)
        return gen2.text.strip(), True

    async def _run_tool_chain(
        self,
        response_text: str,
        user_prompt: str,
        system_prompt: str,
        task_type: str,
        session_id: str | None = None,
    ) -> tuple[str, int]:
        """Multi-step agentic tool loop: execute up to _MAX_TOOL_STEPS TOOL_CALLs.

        Returns (final_response, steps_taken).  If the initial response contains
        no TOOL_CALL, returns it unchanged with steps_taken=0.  Loop detection
        breaks the chain when the identical (tool, args) pair repeats.

        ``session_id`` is forwarded to each re-generation call so its outbound
        HTTP traffic is attributed correctly in the privacy audit log.
        """
        if self._tool_registry is None:
            return response_text, 0

        from neuralcleave.tools.call_parser import parse as _parse_call

        context = user_prompt
        seen: set[str] = set()
        steps = 0
        current_text = response_text

        for _ in range(self._max_tool_steps):
            call = _parse_call(current_text)
            if call is None:
                if "TOOL_CALL:" not in current_text:
                    break
                logger.warning("pipeline: malformed TOOL_CALL in chain step %d", steps + 1)
                current_text = "I tried to use a tool but ran into a formatting issue. Could you rephrase?"
                break

            loop_key = f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"
            if loop_key in seen:
                logger.warning("pipeline: tool chain loop detected on %r — stopping", call.name)
                cleaned = re.sub(r"^TOOL_CALL:.*$", "", current_text, flags=re.MULTILINE).strip()
                current_text = cleaned or "I wasn't able to complete that with the available tools."
                break
            seen.add(loop_key)

            result = await self._tool_registry.call(
                call.name, call.arguments, session_id=session_id or ""
            )
            try:
                from neuralcleave.observability.metrics import REGISTRY
                REGISTRY.inc("tool_calls_total")
            except Exception:
                pass

            steps += 1
            context = f"{context}\n\n{result.to_prompt_block()}"
            gen = await self._router.generate(
                context, task_type=task_type, system=system_prompt, session_id=session_id
            )
            current_text = gen.text.strip()
        else:
            if "TOOL_CALL:" in current_text:
                cleaned = re.sub(r"^TOOL_CALL:.*$", "", current_text, flags=re.MULTILINE).strip()
                current_text = cleaned or "I couldn't complete that request in the available steps."

        if steps > 0:
            try:
                from neuralcleave.observability.metrics import REGISTRY
                REGISTRY.observe("tool_chain_depth", steps)
            except Exception:
                pass

        return current_text, steps

    def _build_system(self, ctx: RetrievalContext, session: Session) -> str:
        from datetime import datetime
        _now = datetime.now()
        # %-d (no-zero-pad) is Linux-only; build the day string portably.
        today = _now.strftime(f"%A, %B {_now.day}, %Y")
        parts: list[str] = [
            self._workspace.to_system_prompt(self._agent_name),
            f"# Current date\nToday is {today}.",
        ]

        memory_blocks = ctx.to_prompt_blocks()
        if memory_blocks:
            parts.append("# Relevant memory\n" + "\n\n".join(memory_blocks))

        if self._tool_registry is not None and self._tool_registry.names:
            parts.append(_tools_system_block(self._tool_registry))

        return "\n\n".join(parts)

    def _build_user(self, text: str, session: Session) -> str:
        history = session.build_prompt(include_turns=10)
        if history:
            return f"{history}\nUser: {text}"
        return text

    # ------------------------------------------------------------------
    # Intent extraction
    # ------------------------------------------------------------------

    async def _extract_intent(self, text: str) -> str:
        if len(text) < 5:
            return "chat"
        try:
            result = await self._router.generate(
                f"""Classify this user message into ONE of these intents:
code, debug, explain, summarize, plan, search, translate, calculate, convert, list, write, question, chat, other

Message: {text[:500]}

Reply with ONLY the intent word, nothing else.""",
                task_type="intent_extraction",
                max_tokens=10,
                temperature=0.0,
            )
            intent = result.text.strip().lower().split()[0]
            return intent if intent in INTENT_TASK_MAP else "chat"
        except Exception as exc:
            logger.debug("intent_extraction failed (%s), using 'chat'", exc)
            return "chat"
