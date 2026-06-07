"""Memory API — search, store, and delete memory entries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.permission_engine import get_current_user
from app.db.models.agent import Agent
from app.db.models.memory import MemoryEntry
from app.db.models.user import User
from app.db.postgres import get_db
from app.schemas.memory import (
    MemoryResponse,
    MemorySearchResponse,
    MemoryStoreRequest,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/memory")

_EMBEDDING_MODEL: Any = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
    return {
        "memory_id": str(entry.id),
        "memory_type": entry.memory_type,
        "content": entry.content,
        "importance_score": entry.importance_score,
        "agent_id": str(entry.agent_id) if entry.agent_id else None,
        "tags": entry.tags or [],
        "created_at": (
            entry.created_at.isoformat()
            if entry.created_at
            else datetime.now(timezone.utc).isoformat()
        ),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/search", response_model=MemorySearchResponse)
async def search_memory(
    q: str = Query(..., min_length=1, max_length=512, description="Search query"),
    agent_id: str | None = Query(default=None, description="Filter by agent ID"),
    memory_type: str | None = Query(default=None, description="Filter by memory type"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Search memory entries using full-text matching on content.

    In production this delegates to the MemoryRetrievalPipeline for
    semantic vector search via Qdrant.
    """
    if agent_id:
        try:
            aid = uuid.UUID(agent_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format"
            )

        from app.core.memory.retrieval import MemoryRetrievalPipeline

        # Calculate embedding
        try:
            from sentence_transformers import SentenceTransformer

            global _EMBEDDING_MODEL
            if _EMBEDDING_MODEL is None:
                _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            import asyncio

            loop = asyncio.get_running_loop()
            embedding = await loop.run_in_executor(
                None, lambda: _EMBEDDING_MODEL.encode(q).tolist()
            )
        except Exception as e:
            logger.warning("Failed to generate embedding for query: %s", e)
            embedding = None

        pipeline = MemoryRetrievalPipeline(agent_id=aid)
        # Run unified retrieval
        retrieved_context = await pipeline.retrieve(
            query=q,
            embedding=embedding,
            top_k=limit,
            db=db,
            extra_episodic_filter={"memory_type": memory_type} if memory_type else None,
        )

        # Map pipeline MemoryResult objects to schema structure
        results = []
        for r in retrieved_context.results:
            results.append(
                {
                    "memory_id": r.metadata.get("id")
                    or r.metadata.get("point_id")
                    or str(uuid.uuid4()),
                    "memory_type": r.metadata.get("memory_type") or r.source,
                    "content": r.content if isinstance(r.content, str) else str(r.content),
                    "importance_score": r.score,
                    "agent_id": str(aid),
                    "tags": r.metadata.get("tags") or [],
                    "created_at": r.metadata.get("created_at")
                    or datetime.now(timezone.utc).isoformat(),
                }
            )

        return {
            "query": q,
            "results": results,
            "total": len(results),
        }

    stmt = select(MemoryEntry).where(MemoryEntry.content.ilike(f"%{q}%"))

    if memory_type:
        stmt = stmt.where(MemoryEntry.memory_type == memory_type)

    stmt = stmt.order_by(MemoryEntry.importance_score.desc()).limit(limit)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    return {
        "query": q,
        "results": [_entry_to_dict(e) for e in entries],
        "total": len(entries),
    }


@router.post("/store", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def store_memory(
    body: MemoryStoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Store a new memory entry."""
    agent_id = None
    if body.agent_id:
        try:
            agent_id = uuid.UUID(body.agent_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format"
            )

    entry = MemoryEntry(
        content=body.content,
        memory_type=body.memory_type,
        agent_id=agent_id,
        importance_score=body.importance_score,
        tags=body.tags,
        metadata_=body.metadata,
    )
    db.add(entry)
    await db.flush()
    logger.info("memory_stored", memory_id=str(entry.id), memory_type=body.memory_type)

    if agent_id:
        try:
            from sentence_transformers import SentenceTransformer

            global _EMBEDDING_MODEL
            if _EMBEDDING_MODEL is None:
                _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            import asyncio

            loop = asyncio.get_running_loop()

            text_to_embed = body.content if isinstance(body.content, str) else str(body.content)
            embedding = await loop.run_in_executor(
                None, lambda: _EMBEDDING_MODEL.encode(text_to_embed).tolist()
            )

            from app.core.memory.retrieval import MemoryRetrievalPipeline

            pipeline = MemoryRetrievalPipeline(agent_id=agent_id)
            await pipeline.store_episodic(
                embedding=embedding,
                payload={
                    "memory_id": str(entry.id),
                    "memory_type": body.memory_type,
                    "content": body.content,
                    "tags": body.tags or [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                deduplicate=True,
            )
        except Exception as exc:
            logger.warning("graph_vector_store_failed", memory_id=str(entry.id), error=str(exc))

    return _entry_to_dict(entry)


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a memory entry by ID."""
    try:
        mid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid memory_id format"
        )

    # Join to Agent to enforce ownership — any user can otherwise delete any entry (BUG-003)
    result = await db.execute(
        select(MemoryEntry)
        .join(Agent, Agent.id == MemoryEntry.agent_id)
        .where(MemoryEntry.id == mid)
        .where(Agent.owner_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found")

    await db.delete(entry)
    logger.info("memory_deleted", memory_id=memory_id)
