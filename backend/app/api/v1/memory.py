"""Memory API — search, store, and delete memory entries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from app.schemas.memory import (
    MemoryResponse,
    MemorySearchResponse,
    MemoryStoreRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.permission_engine import get_current_user
from app.db.models.memory import MemoryEntry
from app.db.models.user import User
from app.db.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/memory")


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
        "created_at": entry.created_at.isoformat() if entry.created_at else datetime.now(timezone.utc).isoformat(),
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
    stmt = select(MemoryEntry).where(MemoryEntry.content.ilike(f"%{q}%"))

    if agent_id:
        try:
            aid = uuid.UUID(agent_id)
            stmt = stmt.where(MemoryEntry.agent_id == aid)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

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
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

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
    return _entry_to_dict(entry)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a memory entry by ID."""
    try:
        mid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid memory_id format")

    result = await db.execute(select(MemoryEntry).where(MemoryEntry.id == mid))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found")

    await db.delete(entry)
    logger.info("memory_deleted", memory_id=memory_id)
