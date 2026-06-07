"""Observability API — logs, metrics, traces, and live agent graphs."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.observability.logs import get_log_buffer
from app.core.observability.metrics import PROMETHEUS_AVAILABLE, get_metrics
from app.core.security.permission_engine import get_current_user
from app.db.models.user import User
from app.schemas.observability import (
    AgentGraphResponse,
    LogEntryResponse,
    MetricsResponse,
    TraceResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/observability")


def _collect_counter_total(counter: Any) -> int:
    """Sum all sample values for a Prometheus counter across all label combinations."""
    total = 0
    try:
        for metric_family in counter.collect():
            for sample in metric_family.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception:
        pass
    return total


def _collect_gauge_total(gauge: Any) -> float:
    """Sum all sample values for a Prometheus gauge across all label combinations."""
    total = 0.0
    try:
        for metric_family in gauge.collect():
            for sample in metric_family.samples:
                total += sample.value
    except Exception:
        pass
    return total


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/logs", response_model=list[LogEntryResponse])
async def get_logs(
    min_level: str = Query(
        default="INFO", description="Minimum log level: DEBUG | INFO | WARNING | ERROR | CRITICAL"
    ),
    agent_id: str | None = Query(default=None, description="Filter logs by agent ID"),
    workflow_id: str | None = Query(default=None, description="Filter logs by workflow ID"),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return recent structured log entries from the in-process log buffer."""
    buf = get_log_buffer()
    entries = buf.query(
        min_level=min_level,
        agent_id=agent_id or None,
        workflow_id=workflow_id or None,
        limit=limit,
    )
    return [
        {
            "level": e.level,
            "message": e.message,
            "logger": e.logger_name,
            "timestamp": e.timestamp.isoformat(),
            "trace_id": e.trace_id,
            "agent_id": e.agent_id,
            "workflow_id": e.workflow_id,
        }
        for e in entries
    ]


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics_summary(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return a point-in-time snapshot of runtime metrics."""
    m = get_metrics()

    if PROMETHEUS_AVAILABLE:
        tool_calls_total = _collect_counter_total(m.tool_calls_total)
        workflow_runs_total = _collect_counter_total(m.workflow_runs_total)
        llm_requests_total = _collect_counter_total(m.llm_requests_total)
        active_agents = int(_collect_gauge_total(m.agents_active))
    else:
        tool_calls_total = 0
        workflow_runs_total = 0
        llm_requests_total = 0
        active_agents = 0

    return {
        "tool_calls_total": tool_calls_total,
        "workflow_runs_total": workflow_runs_total,
        "llm_requests_total": llm_requests_total,
        "active_agents": active_agents,
        "snapshot": {
            "prometheus_available": PROMETHEUS_AVAILABLE,
            "note": "Full time-series metrics are available at the /metrics Prometheus scrape endpoint.",
        },
    }


@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(
    trace_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Retrieve spans for a given trace ID from the in-process log buffer.

    Full distributed trace data is exported to the configured OTLP backend
    (Jaeger / Tempo). This endpoint surfaces log entries tagged with the
    requested trace_id as a lightweight fallback.
    """
    buf = get_log_buffer()
    log_entries = buf.query(limit=500)
    spans = []
    for e in log_entries:
        if e.trace_id and e.trace_id == trace_id:
            spans.append(
                {
                    "span_id": e.trace_id,
                    "operation": e.message,
                    "timestamp": e.timestamp.isoformat(),
                    "level": e.level,
                    "agent_id": e.agent_id,
                    "workflow_id": e.workflow_id,
                }
            )

    return {"trace_id": trace_id, "spans": spans}


@router.get("/agents/{agent_id}/graph", response_model=AgentGraphResponse)
async def get_agent_graph(
    agent_id: str,
    depth: int = Query(
        default=2, ge=1, le=5, description="Max traversal depth for collaboration graph"
    ),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the collaboration graph for a specific agent from the knowledge graph.

    Nodes are collaborating agents reachable within *depth* hops via
    COMMUNICATES_WITH edges. Edges represent direct communication links.
    """
    try:
        aid = uuid.UUID(agent_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format"
        )

    nodes: list[dict] = [{"id": agent_id, "type": "root"}]
    edges: list[dict] = []

    try:
        from app.core.memory.knowledge_graph import KnowledgeGraphMemory

        graph = KnowledgeGraphMemory()
        collaborators = await graph.get_collaborating_agents(aid, depth=depth)
        for c in collaborators:
            collab_id = str(c["id"])
            nodes.append(
                {
                    "id": collab_id,
                    "name": c.get("name", ""),
                    "type": c.get("type", "unknown"),
                    "hops": c.get("hops", 1),
                }
            )
            edges.append({"source": agent_id, "target": collab_id, "hops": c.get("hops", 1)})
    except Exception as exc:
        logger.warning("agent_graph_fetch_failed", agent_id=agent_id, error=str(exc))

    return {"agent_id": agent_id, "nodes": nodes, "edges": edges}
