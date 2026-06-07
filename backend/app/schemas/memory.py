"""Pydantic schemas for Memory endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryStoreRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=65536)
    memory_type: str = Field(
        default="episodic", pattern=r"^(short_term|semantic|episodic|knowledge_graph)$"
    )
    agent_id: str | None = Field(default=None)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryResponse(BaseModel):
    memory_id: str
    memory_type: str
    content: str
    importance_score: float
    agent_id: str | None
    tags: list[str]
    created_at: str


class MemorySearchResponse(BaseModel):
    query: str
    results: list[MemoryResponse]
    total: int
