"""Pydantic schemas for Workflow endpoints."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class WorkflowRunRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    dag_definition: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = Field(default=None)
    trigger_source: str = Field(default="manual", max_length=100)


class WorkflowResponse(BaseModel):
    workflow_id: str
    name: str
    status: str
    version: int
    owner_id: str
    agent_id: str | None
    trigger_source: str | None
    created_at: str
    dag_definition: dict[str, Any]


class WorkflowActionResponse(BaseModel):
    workflow_id: str
    action: str
    status: str
    message: str


class DagUpdateRequest(BaseModel):
    dag_definition: dict[str, Any] = Field(..., description="React Flow nodes/edges DAG definition")
