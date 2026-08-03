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
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from neuralcleave.agent.session import Session
from neuralcleave.channels.base import InboundMessage
from neuralcleave.memory.retrieval import MemoryRetrievalPipeline, RetrievalContext
from neuralcleave.models.router import GenerationResult, ModelRouter
from neuralcleave.reflection.engine import ReflectionEngine
from neuralcleave.tools.registry import ToolRegistry
from neuralcleave.workspace import WorkspaceFiles

logger = logging.getLogger(__name__)

# Intent labels understood by the pipeline
INTENT_TASK_MAP: dict[str, str] = {
    "code": "code_generation",
    "debug": "code_review",
    "explain": "summarization",
    "summarize": "summarization",
    "plan": "task_decomposition",
    "write": "general",
    "question": "general",
    "chat": "general",
    "other": "general",
}


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
    """

    def __init__(
        self,
        router: ModelRouter,
        memory: MemoryRetrievalPipeline,
        workspace: WorkspaceFiles,
        agent_name: str = "NeuralCleave",
        reflection: ReflectionEngine | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._router = router
        self._memory = memory
        self._workspace = workspace
        self._agent_name = agent_name
        self._reflection = reflection
        self._tool_registry = tool_registry

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
        ctx = await self._memory.retrieve(text, top_k=8, session_id=session.session_id)

        # ── Stage 3: Prompt assembly ────────────────────────────────────
        system_prompt = self._build_system(ctx, session)
        user_prompt = self._build_user(text, session)

        # ── Stage 4: Generation ─────────────────────────────────────────
        gen: GenerationResult = await self._router.generate(
            user_prompt,
            task_type=task_type,
            system=system_prompt,
        )
        response_text = gen.text.strip()

        # ── Stage 4b: Tool call execution (if any) ──────────────────────
        if self._tool_registry is not None:
            response_text, _ = await self._run_tool_if_called(
                response_text, user_prompt, system_prompt, task_type
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

        # ── Stage 7: Persist short-term memory (fire-and-forget) ───────
        asyncio.create_task(
            self._memory.store_short_term(
                key=f"turn:{session.turn_count}",
                value={"user": text, "assistant": response_text},
                session_id=session.session_id,
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
        ctx = await self._memory.retrieve(text, top_k=8, session_id=session.session_id)
        system_prompt = self._build_system(ctx, session)
        user_prompt = self._build_user(text, session)

        accumulated: list[str] = []
        final_model = ""
        final_provider = ""
        final_usage: dict[str, int] = {}
        stream_error: str | None = None

        # When tools are registered, buffer the first generation so we can
        # detect TOOL_CALL markers before yielding text to the caller.
        _has_tools = self._tool_registry is not None and bool(self._tool_registry.names)

        async for chunk in self._router.generate_stream(
            user_prompt, task_type=task_type, system=system_prompt
        ):
            if chunk.error:
                stream_error = chunk.error
                break
            if chunk.text:
                accumulated.append(chunk.text)
                if not _has_tools:
                    yield PipelineStreamChunk(text=chunk.text)
            if chunk.done:
                final_model = chunk.model or ""
                final_provider = chunk.provider or ""
                final_usage = chunk.usage

        if stream_error:
            yield PipelineStreamChunk(done=True, error=stream_error)
            return

        response_text = "".join(accumulated).strip()

        # Tool call handling — execute and re-generate when a TOOL_CALL is found.
        if _has_tools:
            response_text, _ = await self._run_tool_if_called(
                response_text, user_prompt, system_prompt, task_type
            )
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

        asyncio.create_task(
            self._memory.store_short_term(
                key=f"turn:{session.turn_count}",
                value={"user": text, "assistant": response_text},
                session_id=session.session_id,
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
        )
        yield PipelineStreamChunk(done=True, result=result)

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
            return response_text, False

        result = await self._tool_registry.call(call.name, call.arguments)
        try:
            from neuralcleave.observability.metrics import REGISTRY
            REGISTRY.inc("tool_calls_total")
        except Exception:
            pass

        augmented = f"{user_prompt}\n\n{result.to_prompt_block()}"
        gen2 = await self._router.generate(augmented, task_type=task_type, system=system_prompt)
        return gen2.text.strip(), True

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
code, debug, explain, summarize, plan, write, question, chat, other

Message: {text[:500]}

Reply with ONLY the intent word, nothing else.""",
                task_type="intent_extraction",
                max_tokens=10,
                temperature=0.0,
            )
            intent = result.text.strip().lower().split()[0]
            return intent if intent in INTENT_TASK_MAP else "other"
        except Exception as exc:
            logger.debug("intent_extraction failed (%s), using 'general'", exc)
            return "other"
