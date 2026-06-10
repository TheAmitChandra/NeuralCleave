"""Cognitive pipeline: intent extraction → memory retrieval → generation → reflection.

The pipeline is the heart of CortexFlow's intelligence layer. Each inbound
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
from dataclasses import dataclass

from cortexflow.channels.base import InboundMessage
from cortexflow.agent.session import Session
from cortexflow.memory.retrieval import MemoryRetrievalPipeline, RetrievalContext
from cortexflow.models.router import ModelRouter, GenerationResult
from cortexflow.reflection.engine import ReflectionEngine
from cortexflow.workspace import WorkspaceFiles

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
        agent_name: str = "CortexFlow",
        reflection: ReflectionEngine | None = None,
    ) -> None:
        self._router = router
        self._memory = memory
        self._workspace = workspace
        self._agent_name = agent_name
        self._reflection = reflection

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
        ctx = await self._memory.retrieve(text, top_k=8)

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
        )

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_system(self, ctx: RetrievalContext, session: Session) -> str:
        parts: list[str] = [self._workspace.to_system_prompt(self._agent_name)]

        memory_blocks = ctx.to_prompt_blocks()
        if memory_blocks:
            parts.append("# Relevant memory\n" + "\n\n".join(memory_blocks))

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
