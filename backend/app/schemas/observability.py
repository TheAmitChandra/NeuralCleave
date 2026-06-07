"""Pydantic schemas for Observability endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LogEntryResponse(BaseModel):
    level: str
    message: str
    logger: str
    timestamp: str
    trace_id: str
    agent_id: str
    workflow_id: str


class MetricsResponse(BaseModel):
    tool_calls_total: int
    workflow_runs_total: int
    llm_requests_total: int
    active_agents: int
    snapshot: dict[str, Any]


class TraceResponse(BaseModel):
    trace_id: str
    spans: list[dict[str, Any]]


class AgentGraphResponse(BaseModel):
    agent_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
