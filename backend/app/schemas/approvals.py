"""Pydantic schemas for Approvals endpoints."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ApprovalResponse(BaseModel):
    request_id: str
    actor_id: str
    tool_name: str
    tool_params: dict[str, Any]
    action_description: str
    risk_score: int
    priority: str
    status: str
    tenant_id: str
    created_at: str
    expires_at: str
    decided_at: str | None
    decided_by: str | None
    rejection_reason: str | None
    context: dict[str, Any]
    request_hash: str


class RejectRequest(BaseModel):
    reason: str = Field(default="", max_length=1024)


class CancelRequest(BaseModel):
    actor_id: str = Field(..., min_length=1, max_length=128)
