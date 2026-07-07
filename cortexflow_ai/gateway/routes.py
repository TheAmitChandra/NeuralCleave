"""REST API routes for the CortexFlow web UI and external integrations.

Mounts under the ``/api/v1`` prefix. All endpoints return JSON.

Routes:

  GET  /api/v1/status              — gateway status + session count + uptime
  GET  /api/v1/sessions            — list active WebSocket sessions
  DELETE /api/v1/sessions/{id}     — disconnect a session
  GET  /api/v1/agent/sessions      — list active per-user channel sessions (AI state)

  GET  /api/v1/channels            — list registered channel adapters
  GET  /api/v1/channels/{id}       — single channel info
  POST /api/v1/channels/{id}/send  — send a message via a channel
  POST /api/v1/channels/{id}/read  — mark a channel's unread count as 0

  GET  /api/v1/memory/search       — search long-term memory (query param)
  GET  /api/v1/memory/entries      — list recent long-term memory entries
  PATCH /api/v1/memory/entries/{id} — edit a memory entry's content/importance
  DELETE /api/v1/memory/entries/{id} — delete a single memory entry
  POST /api/v1/memory/prune        — manually trigger memory GC (delete old + low-importance)

  GET  /api/v1/metrics             — Prometheus text exposition format
  GET  /api/v1/metrics/snapshot    — machine-readable JSON metrics snapshot

  POST /api/v1/settings/llm        — apply LLM credentials to the running ModelRouter
  POST /api/v1/settings/model      — set active provider, privacy mode

The channel, memory, and settings routes require a running AgentRuntime. If the
runtime is not injected, they return 503 Service Unavailable.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from cortexflow_ai import __version__
from cortexflow_ai.gateway.websocket import get_manager
from cortexflow_ai.observability.metrics import REGISTRY

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
        "version": __version__,
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


@router.get("/agent/sessions")
async def list_agent_sessions() -> dict[str, Any]:
    """List active per-user channel sessions (the AI's conversation state).

    These are distinct from ``/sessions`` (WebSocket UI connections). Each
    entry here represents one user on one channel — it holds conversation
    history, voice mode, and idle time. Returns 503 when the runtime is
    not available.
    """
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    sessions_mgr = getattr(rt, "_sessions", None)
    if sessions_mgr is None:
        return {"sessions": [], "count": 0}

    sessions = [
        {
            "session_id": s.session_id,
            "channel": s.channel,
            "sender_id": s.sender_id,
            "turn_count": s.turn_count,
            "idle_seconds": round(s.idle_seconds, 1),
            "voice_mode": s.voice_mode,
        }
        for s in sessions_mgr._sessions.values()
    ]
    return {"sessions": sessions, "count": len(sessions)}


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
            "connected": adapter.is_connected,
            "unread": rt.get_unread_count(cid),
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


@router.post("/channels/{channel_id}/read")
async def mark_channel_read(channel_id: str) -> dict[str, Any]:
    """Reset a channel's unread count to 0 (called when the user views it)."""
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    adapters = getattr(rt, "_adapters", {})
    if channel_id not in adapters:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id!r} not found")

    rt.mark_channel_read(channel_id)
    return {"channel_id": channel_id, "unread": 0}


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@router.get("/memory/search")
async def search_memory(
    q: str = Query(..., description="Search query"),
    session_id: str | None = Query(None, description="Session ID filter (omit for all sessions)"),
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
    session_id: str | None = Query(None, description="Session ID filter (omit for all sessions)"),
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


@router.patch("/memory/entries/{entry_id}")
async def edit_memory_entry(entry_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Edit a memory entry's content and/or importance score.

    Body: ``{"content": "<new text>", "importance": 0.0-1.0}`` — both
    optional, but at least one must be provided.
    """
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

    content = body.get("content")
    importance = body.get("importance")
    if content is None and importance is None:
        raise HTTPException(status_code=422, detail="Provide 'content' and/or 'importance'")

    results: list[bool] = []
    if content is not None:
        results.append(await long_term.update_content(eid, content))
    if importance is not None:
        results.append(await long_term.update_importance(eid, float(importance)))

    if not any(results):
        raise HTTPException(status_code=404, detail=f"Memory entry {entry_id!r} not found")

    return {"id": eid, "updated": True}


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


@router.post("/memory/prune")
async def prune_memory(body: dict[str, Any] = {}) -> dict[str, Any]:  # noqa: B006
    """Manually trigger long-term memory pruning.

    Body keys (all optional):
    - ``days``:      Delete entries not accessed in the last N days (default 90).
    - ``threshold``: Delete entries with importance score below this value (default 0.1).
    """
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    long_term = getattr(rt, "_long_term", None)
    if long_term is None:
        raise HTTPException(status_code=503, detail="Long-term memory not configured")

    days = int(body.get("days", 90))
    threshold = float(body.get("threshold", 0.1))

    old_removed = await long_term.delete_old(days=days)
    low_removed = await long_term.prune_low_importance(threshold=threshold)

    return {
        "pruned": True,
        "stale_removed": old_removed,
        "low_importance_removed": low_removed,
        "total_removed": old_removed + low_removed,
    }


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


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

_LLM_FIELD_MAP: dict[str, str] = {
    "gemini_api_key": "_gemini_key",
    "deepseek_api_key": "_deepseek_key",
    "anthropic_api_key": "_anthropic_key",
    "openai_api_key": "_openai_key",
    "ollama_base_url": "_ollama_url",
}


@router.post("/settings/llm")
async def apply_llm_settings(body: dict[str, Any]) -> dict[str, Any]:
    """Apply LLM provider credentials to the running ModelRouter.

    Body keys (all optional, but at least one must be present):
    ``gemini_api_key``, ``deepseek_api_key``, ``anthropic_api_key``,
    ``openai_api_key``, ``ollama_base_url``
    """
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    pipeline = getattr(rt, "_pipeline", None)
    model_router = getattr(pipeline, "_router", None) if pipeline is not None else None
    if model_router is None:
        raise HTTPException(status_code=503, detail="ModelRouter not accessible")

    updated: list[str] = []
    for key, attr in _LLM_FIELD_MAP.items():
        if body.get(key):
            setattr(model_router, attr, body[key])
            updated.append(key)

    if not updated:
        raise HTTPException(status_code=422, detail="Provide at least one recognized setting")

    return {"applied": True, "updated_fields": updated}


_VALID_PROVIDERS = {"gemini", "anthropic", "openai", "deepseek", "ollama"}


@router.post("/settings/model")
async def apply_model_settings(body: dict[str, Any]) -> dict[str, Any]:
    """Apply model routing settings to the running ModelRouter.

    Body keys (all optional, but at least one must be present):
    - ``provider``:      Force all requests through this provider
      (``"gemini"``, ``"anthropic"``, ``"openai"``, ``"deepseek"``, ``"ollama"``).
      Pass ``null`` or omit to restore automatic task-based routing.
    - ``privacy_mode``:  Boolean — route everything to local Ollama.
    """
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    pipeline = getattr(rt, "_pipeline", None)
    model_router = getattr(pipeline, "_router", None) if pipeline is not None else None
    if model_router is None:
        raise HTTPException(status_code=503, detail="ModelRouter not accessible")

    applied: dict[str, Any] = {}

    provider = body.get("provider")
    if "provider" in body:
        if provider is None:
            model_router._forced_provider = None
            applied["provider"] = None
        elif isinstance(provider, str) and provider in _VALID_PROVIDERS:
            model_router._forced_provider = provider
            applied["provider"] = provider
        else:
            raise HTTPException(
                status_code=422,
                detail=f"provider must be one of {sorted(_VALID_PROVIDERS)} or null",
            )

    if "privacy_mode" in body:
        val = body["privacy_mode"]
        if not isinstance(val, bool):
            raise HTTPException(status_code=422, detail="privacy_mode must be a boolean")
        model_router.privacy_mode = val
        applied["privacy_mode"] = val

    if not applied:
        raise HTTPException(status_code=422, detail="Provide at least one recognized setting")

    return {"applied": True, "settings": applied}
