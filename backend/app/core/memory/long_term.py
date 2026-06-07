"""Long-term memory backed by PostgreSQL.

Stores structured episodic/semantic memory entries tied to an agent.
Records persist indefinitely (subject to retention policies) and are
queryable by agent, type, and time range.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.memory import MemoryEntry


class LongTermMemory:
    """PostgreSQL-backed persistent memory for an agent.

    Each entry stores a structured JSONB payload plus an optional
    ``embedding_id`` pointing to the corresponding Qdrant vector.
    """

    def __init__(self, agent_id: UUID, session: AsyncSession) -> None:
        self.agent_id = agent_id
        self.session = session

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def store(
        self,
        content: dict[str, Any],
        memory_type: str = "episodic",
        embedding_id: str | None = None,
    ) -> MemoryEntry:
        """Persist a memory entry and return the saved ORM object."""
        entry = MemoryEntry(
            agent_id=self.agent_id,
            memory_type=memory_type,
            content=content,
            embedding_id=embedding_id,
        )
        self.session.add(entry)
        await self.session.flush()  # populate entry.id without committing
        return entry

    async def get(self, memory_id: UUID) -> MemoryEntry | None:
        """Retrieve a single memory entry by primary key."""
        result = await self.session.execute(
            select(MemoryEntry).where(
                MemoryEntry.id == memory_id,
                MemoryEntry.agent_id == self.agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        memory_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """Return memory entries with optional type/time filters."""
        stmt = (
            select(MemoryEntry)
            .where(MemoryEntry.agent_id == self.agent_id)
            .order_by(MemoryEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if memory_type:
            stmt = stmt.where(MemoryEntry.memory_type == memory_type)
        if since:
            stmt = stmt.where(MemoryEntry.created_at >= since)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_embedding_id(self, memory_id: UUID, embedding_id: str) -> None:
        """Link a memory entry to its Qdrant vector after embedding is stored."""
        entry = await self.get(memory_id)
        if entry:
            entry.embedding_id = embedding_id

    async def delete(self, memory_id: UUID) -> None:
        """Hard-delete a specific memory entry."""
        await self.session.execute(
            delete(MemoryEntry).where(
                MemoryEntry.id == memory_id,
                MemoryEntry.agent_id == self.agent_id,
            )
        )

    async def purge_older_than(self, before: datetime, memory_type: str | None = None) -> int:
        """Delete entries older than *before*. Returns the number of rows deleted."""
        stmt = delete(MemoryEntry).where(
            MemoryEntry.agent_id == self.agent_id,
            MemoryEntry.created_at < before,
        )
        if memory_type:
            stmt = stmt.where(MemoryEntry.memory_type == memory_type)
        result = await self.session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Importance scoring helper
    # ------------------------------------------------------------------

    @staticmethod
    def importance_score(
        recency: float,
        access_count: int,
        relevance_score: float,
        *,
        recency_weight: float = 0.4,
        access_weight: float = 0.3,
        relevance_weight: float = 0.3,
    ) -> float:
        """Compute a composite importance score in [0, 1].

        Args:
            recency: Normalised age factor (1.0 = now, 0.0 = oldest).
            access_count: Number of times this memory has been retrieved.
            relevance_score: Semantic relevance from the last retrieval (0–1).
        """
        normalised_access = min(access_count / 100, 1.0)
        return (
            recency_weight * recency
            + access_weight * normalised_access
            + relevance_weight * relevance_score
        )
