"""Session archiving — condense inactive sessions into one searchable summary.

Distinct from ConversationCompactor (which compresses an *active*
session's live in-memory history mid-conversation): this operates on
already-persisted long-term memory rows for sessions that have gone
quiet, replacing many small entries with one dense LLM-generated
archive summary so the database doesn't grow unbounded with stale detail
while still keeping the gist searchable.

Usage::

    archiver = SessionArchiver(long_term=LongTermMemory(), router=model_router)

    # Archive one session immediately
    summary = await archiver.archive_session("user-123")

    # Archive every session inactive for 30+ days
    archived = await archiver.archive_inactive_sessions(older_than_days=30)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cortexflow.memory.long_term import LongTermMemory
    from cortexflow.models.router import ModelRouter

_ARCHIVE_IMPORTANCE = 0.7
_ARCHIVE_MEMORY_TYPE = "archive_summary"
_FETCH_LIMIT = 1000

_ARCHIVE_PROMPT = """\
You are archiving memory from an inactive conversation session. Given the
memory entries below, write a dense, factual summary covering:
- Key facts, decisions, and preferences learned about the user
- Important dates, names, and numbers
- Anything that should still be remembered long-term

Respond ONLY with the summary text — no headers, no preamble.

Memory entries:
{entries}
"""


class SessionArchiver:
    """Summarizes and replaces a session's long-term memory entries.

    Args:
        long_term: LongTermMemory instance to read entries from / write
                   the archive summary to.
        router:    ModelRouter used to generate the summary text.
    """

    def __init__(self, long_term: "LongTermMemory", router: "ModelRouter") -> None:
        self._long_term = long_term
        self._router = router

    async def archive_session(self, session_id: str) -> str | None:
        """Summarize and replace all of *session_id*'s entries with one archive entry.

        Returns the generated summary, or None if there was nothing to
        archive or summary generation failed.
        """
        entries = await self._long_term.get_by_session(session_id, limit=_FETCH_LIMIT)
        if not entries:
            return None

        entries_text = "\n".join(f"- {e['content']}" for e in entries)
        summary = await self._generate_summary(entries_text)
        if not summary:
            logger.warning("archiver.archive_session summary generation failed session=%s", session_id)
            return None

        for entry in entries:
            await self._long_term.delete_entry(entry["id"])

        await self._long_term.store(
            session_id=session_id,
            content=f"[ARCHIVED SESSION SUMMARY]\n{summary}",
            importance=_ARCHIVE_IMPORTANCE,
            memory_type=_ARCHIVE_MEMORY_TYPE,
            tags=["archive"],
        )

        logger.info(
            "archiver.archived session=%s entries_removed=%d summary_len=%d",
            session_id,
            len(entries),
            len(summary),
        )
        return summary

    async def archive_inactive_sessions(self, older_than_days: int = 30) -> dict[str, str]:
        """Archive every session inactive for more than *older_than_days* days.

        Returns a mapping of session_id -> generated summary for each
        session that was successfully archived.
        """
        stale_sessions = await self._long_term.list_stale_sessions(older_than_days)
        archived: dict[str, str] = {}
        for session_id in stale_sessions:
            summary = await self.archive_session(session_id)
            if summary:
                archived[session_id] = summary
        return archived

    async def _generate_summary(self, entries_text: str) -> str:
        prompt = _ARCHIVE_PROMPT.format(entries=entries_text)
        try:
            result = await self._router.generate(prompt, task_type="summarization")
            return result.text.strip()
        except Exception as exc:
            logger.error("archiver.generate_summary error: %s", exc)
            return ""
