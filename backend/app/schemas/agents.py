"""Pydantic schemas for Agent endpoints."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    agent_type: str = Field(default="generic", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStatusPatch(BaseModel):
    status: str = Field(..., pattern=r"^(IDLE|PAUSED|TERMINATED)$")


class AgentExecuteRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=2048)
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    agent_type: str
    status: str
    owner_id: str
    created_at: str
    metadata: dict[str, Any]

    model_config = {"from_attributes": True}


class AgentExecuteResponse(BaseModel):
    agent_id: str
    task_id: str
    status: str
    message: str
