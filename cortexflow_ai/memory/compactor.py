"""Conversation compactor — summarise and compress long conversation history.

Implements two compaction strategies:

1. **Summary compaction** (``compact()``):
   Replace the current conversation history with a dense LLM-generated
   summary.  The summary is stored in long-term memory as a high-importance
   entry and re-injected as a system turn at the start of the new window.
   Equivalent to Claude's ``/compact`` command.

2. **Auto-compaction** (``maybe_compact()``):
   Called by the agent pipeline after every turn.  Triggers compaction
   automatically when the estimated token count exceeds a configurable
   threshold (default 50 % of the context window).

Usage::

    compactor = ConversationCompactor(
        session=session,
        long_term=LongTermMemory(),
        router=model_router,
    )

    # Manual compact via /compact command
    summary = await compactor.compact()

    # Auto-compact when context is > 50% full (called in pipeline)
    was_compacted = await compactor.maybe_compact(threshold=0.5)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cortexflow_ai.agent.session import Session
    from cortexflow_ai.memory.long_term import LongTermMemory
    from cortexflow_ai.models.router import ModelRouter

# Rough token estimate: 1 token ≈ 4 characters
_CHARS_PER_TOKEN = 4
# Default maximum context tokens (conservative — works for all supported models)
_DEFAULT_CONTEXT_TOKENS = 8_192
# Importance score for compaction summaries stored in long-term memory
_SUMMARY_IMPORTANCE = 0.85

_COMPACT_PROMPT = """\
You are a conversation summariser. Given the conversation history below,
produce a dense, factual summary that preserves:
- All decisions made or tasks completed
- Key facts, names, dates, and numbers mentioned
- Open questions or pending tasks
- The user's tone and preferences

Respond ONLY with the summary text — no headers, no bullet points, no preamble.

Conversation:
{history}
"""


class ConversationCompactor:
    """Summarise and compress a Session's conversation history.

    Args:
        session:        The active Session to compact.
        long_term:      LongTermMemory instance for persisting summaries.
        router:         ModelRouter used to generate the summary.
        context_tokens: Estimated maximum context window in tokens.
    """

    def __init__(
        self,
        session: "Session",
        long_term: "LongTermMemory",
        router: "ModelRouter",
        context_tokens: int = _DEFAULT_CONTEXT_TOKENS,
    ) -> None:
        self._session = session
        self._long_term = long_term
        self._router = router
        self._context_tokens = context_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compact(self) -> str:
        """Summarise the current conversation and replace history with summary.

        Returns the generated summary text.
        """
        history = self._build_history_text()
        if not history.strip():
            logger.debug("compactor.compact no history to compact")
            return ""

        summary = await self._generate_summary(history)
        if not summary:
            logger.warning("compactor.compact summary generation failed")
            return ""

        # Persist summary to long-term memory
        try:
            await self._long_term.init_schema()
            await self._long_term.store(
                session_id=self._session.session_id,
                content=f"[COMPACTED SUMMARY]\n{summary}",
                importance=_SUMMARY_IMPORTANCE,
                memory_type="summary",
            )
        except Exception as exc:
            logger.warning("compactor.persist failed: %s", exc)

        # Replace session history with a single system summary turn
        self._session.clear()
        self._session.add_turn("system", f"[Previous conversation summary]\n{summary}")

        logger.info(
            "compactor.compacted session=%s turns_removed=%d summary_len=%d",
            self._session.session_id,
            self._session.turn_count,
            len(summary),
        )
        return summary

    async def maybe_compact(self, threshold: float = 0.5) -> bool:
        """Auto-compact if estimated token usage exceeds *threshold*.

        Args:
            threshold: Fraction of context window (0–1) that triggers compaction.
                       Default 0.5 = compact when > 50% full.

        Returns True if compaction was performed.
        """
        used = self._estimate_tokens()
        limit = int(self._context_tokens * threshold)

        if used < limit:
            return False

        logger.info(
            "compactor.auto_compact triggered session=%s used=%d limit=%d",
            self._session.session_id,
            used,
            limit,
        )
        await self.compact()
        return True

    @property
    def estimated_tokens(self) -> int:
        """Current estimated token count for the session history."""
        return self._estimate_tokens()

    @property
    def fill_fraction(self) -> float:
        """Fraction of the context window used (0.0–1.0+)."""
        return self._estimate_tokens() / max(self._context_tokens, 1)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_history_text(self) -> str:
        turns = self._session.history
        lines: list[str] = []
        for t in turns:
            role_label = t["role"].upper()
            content = str(t["content"])
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)

    def _estimate_tokens(self) -> int:
        total_chars = sum(len(str(t["content"])) for t in self._session.history)
        return total_chars // _CHARS_PER_TOKEN

    async def _generate_summary(self, history: str) -> str:
        prompt = _COMPACT_PROMPT.format(history=history)
        try:
            result = await self._router.generate(prompt, task_type="summarization")
            return result.text.strip()
        except Exception as exc:
            logger.error("compactor.generate_summary error: %s", exc)
            return ""
