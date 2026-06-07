"""Pydantic schemas for Tools endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolListItem(BaseModel):
    name: str
    description: str
    risk_level: str
    requires_approval: bool
    permissions: list[str]


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=128)
    agent_id: str = Field(..., description="UUID of the agent invoking the tool")
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None)


class ToolExecuteResponse(BaseModel):
    tool_name: str
    agent_id: str
    success: bool
    output: Any
    error: str | None
    risk_score: float
    isolation_tier: str
    execution_ms: float
    requires_approval: bool
