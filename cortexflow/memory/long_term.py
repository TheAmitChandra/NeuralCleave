"""Long-term memory — persistent SQLite storage for important facts and context.

Schema (auto-created on first use)::

    memory_entries(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT    NOT NULL,
        content         TEXT    NOT NULL,
        importance_score REAL   NOT NULL DEFAULT 0.5,
        memory_type     TEXT    NOT NULL DEFAULT 'general',
        created_at      TEXT    NOT NULL,       -- ISO-8601 UTC
        last_accessed_at TEXT   NOT NULL        -- ISO-8601 UTC
    )

Usage::

    lt = LongTermMemory()
    await lt.init_schema()
    entry_id = await lt.store(
        session_id="user-123",
        content="User prefers concise answers.",
        importance=0.9,
        memory_type="preference",
    )
    results = await lt.search(session_id="user-123", query="concise")
    await lt.update_importance(entry_id, score=0.95)
    deleted = await lt.delete_old(days=30)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "~/.cortexflow/memory.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT    NOT NULL,
    content          TEXT    NOT NULL,
    importance_score REAL    NOT NULL DEFAULT 0.5,
    memory_type      TEXT    NOT NULL DEFAULT 'general',
    created_at       TEXT    NOT NULL,
    last_accessed_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_session ON memory_entries (session_id);
CREATE INDEX IF NOT EXISTS idx_mem_importance ON memory_entries (session_id, importance_score DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LongTermMemory:
    """Async SQLite interface for persistent long-term memory entries.

    Args:
        db_path: Path to the SQLite database file. ``~`` is expanded.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = os.path.expanduser(db_path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def init_schema(self) -> None:
        """Create the memory_entries table and indexes if they don't exist.

        Safe to call on every startup — uses CREATE IF NOT EXISTS.
        """
        import aiosqlite  # type: ignore[import]

        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_CREATE_TABLE)
            await db.commit()
        logger.debug("long_term.schema_ready path=%s", self._db_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def store(
        self,
        session_id: str,
        content: str,
        importance: float = 0.5,
        memory_type: str = "general",
    ) -> int:
        """Insert a new memory entry. Returns the auto-assigned row ID."""
        import aiosqlite  # type: ignore[import]

        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO memory_entries
                    (session_id, content, importance_score, memory_type, created_at, last_accessed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, content, importance, memory_type, now, now),
            )
            await db.commit()
            row_id: int = cursor.lastrowid or 0
        logger.debug(
            "long_term.stored id=%d session=%s type=%s importance=%.2f",
            row_id,
            session_id,
            memory_type,
            importance,
        )
        return row_id

    async def update_importance(self, entry_id: int, score: float) -> bool:
        """Update the importance score for an existing entry.

        Returns True if the row was found and updated.
        """
        import aiosqlite  # type: ignore[import]

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "UPDATE memory_entries SET importance_score = ? WHERE id = ?",
                (score, entry_id),
            )
            await db.commit()
            updated = (cursor.rowcount or 0) > 0
        logger.debug("long_term.importance_updated id=%d score=%.2f found=%s", entry_id, score, updated)
        return updated

    async def delete_entry(self, entry_id: int) -> bool:
        """Delete a single memory entry by ID. Returns True if deleted."""
        import aiosqlite  # type: ignore[import]

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM memory_entries WHERE id = ?", (entry_id,)
            )
            await db.commit()
            deleted = (cursor.rowcount or 0) > 0
        return deleted

    async def delete_old(self, days: int) -> int:
        """Remove entries not accessed in the last *days* days.

        Returns count of deleted rows.
        """
        import aiosqlite  # type: ignore[import]

        cutoff = f"datetime('now', '-{days} days')"
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"DELETE FROM memory_entries WHERE last_accessed_at < {cutoff}"  # noqa: S608
            )
            await db.commit()
            count: int = cursor.rowcount or 0
        logger.info("long_term.delete_old days=%d removed=%d", days, count)
        return count

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_session(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch the top entries for a session ordered by importance descending."""
        import aiosqlite  # type: ignore[import]

        rows = []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, session_id, content, importance_score,
                       memory_type, created_at, last_accessed_at
                FROM memory_entries
                WHERE session_id = ?
                ORDER BY importance_score DESC, last_accessed_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ) as cursor:
                async for row in cursor:
                    rows.append(dict(row))

        # Bump last_accessed_at for returned entries
        if rows:
            ids = [r["id"] for r in rows]
            now = _now()
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    f"UPDATE memory_entries SET last_accessed_at = ? WHERE id IN ({','.join('?' * len(ids))})",  # noqa: S608
                    [now, *ids],
                )
                await db.commit()

        return rows

    async def search(
        self,
        session_id: str,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text LIKE search within a session's memory entries.

        Returns rows ordered by importance descending.

        Note: This is a simple LIKE search. For semantic search use the
        Qdrant tier via MemoryRetrievalPipeline.
        """
        import aiosqlite  # type: ignore[import]

        pattern = f"%{query}%"
        rows = []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, session_id, content, importance_score,
                       memory_type, created_at, last_accessed_at
                FROM memory_entries
                WHERE session_id = ? AND content LIKE ?
                ORDER BY importance_score DESC, last_accessed_at DESC
                LIMIT ?
                """,
                (session_id, pattern, limit),
            ) as cursor:
                async for row in cursor:
                    rows.append(dict(row))
        return rows

    async def prune_low_importance(
        self,
        *,
        threshold: float = 0.2,
    ) -> int:
        """Delete entries below an importance threshold. Returns count deleted."""
        import aiosqlite  # type: ignore[import]

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM memory_entries WHERE importance_score < ?",
                (threshold,),
            )
            await db.commit()
            count: int = cursor.rowcount or 0
        logger.info("long_term.pruned threshold=%.2f removed=%d", threshold, count)
        return count
