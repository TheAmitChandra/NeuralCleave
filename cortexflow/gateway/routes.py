"""REST API routes for the CortexFlow web UI and external integrations.

Mounts under the ``/api/v1`` prefix. All endpoints return JSON.

Routes:

  GET  /api/v1/status              — gateway status + session count + uptime
  GET  /api/v1/sessions            — list active WebSocket sessions
  DELETE /api/v1/sessions/{id}     — disconnect a session

  GET  /api/v1/channels            — list registered channel adapters
  GET  /api/v1/channels/{id}       — single channel info
  POST /api/v1/channels/{id}/send  — send a message via a channel

  GET  /api/v1/memory/search       — search long-term memory (query param)
  GET  /api/v1/memory/entries      — list recent long-term memory entries
  DELETE /api/v1/memory/entries/{id} — delete a single memory entry

  GET  /api/v1/metrics             — Prometheus text exposition format
  GET  /api/v1/metrics/snapshot    — machine-readable JSON metrics snapshot

The channel and memory routes require a running AgentRuntime. If the runtime
is not injected, they return 503 Service Unavailable.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from cortexflow.gateway.websocket import get_manager
from cortexflow.observability.metrics import REGISTRY

router = APIRouter(prefix="/api/v1", tags=["REST API"])

# Module-level runtime reference — set by AgentRuntime.start() or tests
_runtime: Any = None
_start_time: float = time.time()


def set_runtime(runtime: Any) -> None:
    """Inject the AgentRuntime so REST routes can access channels + memory."""
    global _runtime
    _runtime = runtime


def get_runtime() -> Any:
    return _runtime


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Gateway health + uptime."""
    manager = get_manager()
    return {
        "status": "ok",
        "version": "2.0.0",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "active_sessions": manager.session_count,
        "runtime_available": _runtime is not None,
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """List all active WebSocket sessions."""
    manager = get_manager()
    sessions = [
        {
            "session_id": sid,
            "channel": s.channel,
            "connected_at": s.connected_at,
            "age_seconds": round(time.time() - s.connected_at, 1),
        }
        for sid, s in manager._sessions.items()
    ]
    return {"sessions": sessions, "count": len(sessions)}


@router.delete("/sessions/{session_id}", status_code=204)
async def disconnect_session(session_id: str) -> None:
    """Disconnect and remove a session by ID."""
    manager = get_manager()
    session = manager._sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    if session.websocket:
        try:
            await session.websocket.close()
        except Exception:
            pass
    manager.remove(session_id)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


@router.get("/channels")
async def list_channels() -> dict[str, Any]:
    """List registered channel adapters and their connection status."""
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    adapters = getattr(rt, "_adapters", {})
    channels = [
        {
            "channel_id": cid,
            "type": type(adapter).__name__,
            "connected": getattr(adapter, "_ws_task", None) is not None
            or getattr(adapter, "_runner", None) is not None
            or getattr(adapter, "_poll_task", None) is not None,
        }
        for cid, adapter in adapters.items()
    ]
    return {"channels": channels, "count": len(channels)}


@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str) -> dict[str, Any]:
    """Get info for a single channel adapter."""
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    adapters = getattr(rt, "_adapters", {})
    adapter = adapters.get(channel_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id!r} not found")

    return {
        "channel_id": channel_id,
        "type": type(adapter).__name__,
        "config_schema": getattr(adapter, "get_config_schema", lambda: {})(),
    }


@router.post("/channels/{channel_id}/send")
async def send_via_channel(
    channel_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Send a message through a channel adapter.

    Body: ``{"target": "<id>", "text": "<message>"}``
    """
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    adapters = getattr(rt, "_adapters", {})
    adapter = adapters.get(channel_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id!r} not found")

    target = body.get("target", "")
    text = body.get("text", "")
    if not target or not text:
        raise HTTPException(status_code=422, detail="'target' and 'text' are required")

    result = await adapter.send(target, text)
    return {"sent": True, "message_id": result}


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@router.get("/memory/search")
async def search_memory(
    q: str = Query(..., description="Search query"),
    session_id: str = Query("%", description="Session ID filter (% = all)"),
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """Search long-term memory."""
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    long_term = getattr(rt, "_long_term", None)
    if long_term is None:
        raise HTTPException(status_code=503, detail="Long-term memory not configured")

    results = await long_term.search(session_id=session_id, query=q, limit=limit)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/memory/entries")
async def list_memory_entries(
    session_id: str = Query("%", description="Session ID filter (% = all)"),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """List recent long-term memory entries."""
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    long_term = getattr(rt, "_long_term", None)
    if long_term is None:
        raise HTTPException(status_code=503, detail="Long-term memory not configured")

    results = await long_term.search(session_id=session_id, query="", limit=limit)
    return {"entries": results, "count": len(results)}


@router.delete("/memory/entries/{entry_id}", status_code=204)
async def delete_memory_entry(entry_id: str) -> None:
    """Delete a single long-term memory entry by ID."""
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    long_term = getattr(rt, "_long_term", None)
    if long_term is None:
        raise HTTPException(status_code=503, detail="Long-term memory not configured")

    try:
        eid = int(entry_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="entry_id must be an integer")

    deleted = await long_term.delete_entry(eid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory entry {entry_id!r} not found")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    """Prometheus text/plain exposition format for scraping."""
    return REGISTRY.export_prometheus()


@router.get("/metrics/snapshot")
async def metrics_snapshot() -> dict[str, Any]:
    """Machine-readable JSON snapshot of all metrics (for web UI)."""
    return REGISTRY.snapshot()
