"""REST API routes for the NeuralCleave web UI and external integrations.

Mounts under the ``/api/v1`` prefix. All endpoints return JSON.

Routes:

  GET  /api/v1/status              — gateway status + session count + uptime
  GET  /api/v1/sessions            — list active WebSocket sessions
  DELETE /api/v1/sessions/{id}     — disconnect a session
  GET  /api/v1/agent/sessions      — list active per-user channel sessions (AI state)
  GET  /api/v1/agent/sessions/{id}/history — conversation turn history for one session
  POST /api/v1/agent/sessions/{id}/reset — clear conversation history for one session

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

  GET  /api/v1/plugins             — list all registered plugins and their status
  GET  /api/v1/plugins/{name}      — info for a single plugin
  POST /api/v1/plugins/reload      — hot-reload all plugins without gateway restart
  POST /api/v1/plugins/{name}/reload — hot-reload a single plugin by name

  POST /api/v1/settings/voice        — write STT backend/model/device to config.toml (restart required)

  GET  /api/v1/voice/listen/status   — whether continuous listening is active
  POST /api/v1/voice/listen/start   — start continuous voice listening
  POST /api/v1/voice/listen/stop    — stop continuous voice listening

  POST /api/v1/voice/ptt/start      — start a push-to-talk recording session
  POST /api/v1/voice/ptt/stop       — stop PTT; transcribe, run pipeline, play TTS
  GET  /api/v1/voice/ptt/status     — is_recording, duration_s, available

  POST /api/v1/settings/llm        — apply LLM credentials to the running ModelRouter
  POST /api/v1/settings/model      — set active provider, privacy mode

  GET  /api/v1/orchestrator/nodes          — list registered agent nodes
  POST /api/v1/orchestrator/nodes          — register a new agent node
  GET  /api/v1/orchestrator/nodes/{name}   — get a single node's config
  DELETE /api/v1/orchestrator/nodes/{name} — remove a node
  PATCH /api/v1/orchestrator/nodes/{name}  — enable or disable a node
  POST /api/v1/orchestrator/route          — route a task and return the selected node
  GET  /api/v1/orchestrator/status         — routing statistics

The channel, memory, and settings routes require a running AgentRuntime. If the
runtime is not injected, they return 503 Service Unavailable.
"""

from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from neuralcleave import __version__
from neuralcleave.gateway.websocket import get_manager
from neuralcleave.observability.metrics import REGISTRY

router = APIRouter(prefix="/api/v1", tags=["REST API"])

# Module-level runtime reference — set by AgentRuntime.start() or tests
_runtime: Any = None
_start_time: float = time.time()

# Startup phase reported by the lifespan background task.
# "starting"  — lifespan not yet yielded (should be very brief)
# "runtime"   — AgentRuntime.from_config() + start() in progress
# "plugins"   — PluginRegistry.load_all() in progress
# "ready"     — all components wired; runtime_available=True
_init_phase: str = "starting"

# Module-level plugin registry reference — set by gateway startup or tests
_plugin_registry: Any = None

# Module-level orchestrator reference — set by gateway startup or tests
_orchestrator: Any = None


def set_init_phase(phase: str) -> None:
    """Update the startup phase reported by /api/v1/status."""
    global _init_phase
    _init_phase = phase


def get_init_phase() -> str:
    return _init_phase


def set_runtime(runtime: Any) -> None:
    """Inject the AgentRuntime so REST routes can access channels + memory."""
    global _runtime
    _runtime = runtime


def get_runtime() -> Any:
    return _runtime


def set_plugin_registry(registry: Any) -> None:
    """Inject the PluginRegistry so plugin routes can access it."""
    global _plugin_registry
    _plugin_registry = registry


def get_plugin_registry() -> Any:
    return _plugin_registry


def set_orchestrator(orchestrator: Any) -> None:
    """Inject the AgentOrchestrator so orchestrator routes can access it."""
    global _orchestrator
    _orchestrator = orchestrator


def get_orchestrator() -> Any:
    return _orchestrator


_hub_installer: Any = None


def set_hub_installer(installer: Any) -> None:
    """Inject the HubInstaller so hub routes can access it."""
    global _hub_installer
    _hub_installer = installer


def get_hub_installer() -> Any:
    return _hub_installer


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Gateway health + uptime."""
    manager = get_manager()
    voice: dict[str, Any] = {
        "stt_available": False,
        "tts_available": False,
        "wake_word_active": False,
    }
    if _runtime is not None:
        voice["stt_available"] = getattr(_runtime, "_stt", None) is not None
        voice["tts_available"] = getattr(_runtime, "_tts", None) is not None
        voice["wake_word_active"] = getattr(_runtime, "_wake_detector", None) is not None
        _cont = getattr(_runtime, "_continuous", None)
        voice["continuous_listening"] = getattr(_cont, "is_listening", False) if _cont is not None else False
    return {
        "status": "ok",
        "version": __version__,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "active_sessions": manager.session_count,
        "runtime_available": _runtime is not None,
        "init_phase": _init_phase,  # "starting"|"runtime"|"plugins"|"ready"
        "voice": voice,
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


@router.get("/agent/sessions/{session_id}/history")
async def get_agent_session_history(session_id: str) -> dict[str, Any]:
    """Return the in-memory conversation turn history for one agent session.

    Each turn has ``role`` (user/assistant/system), ``content``, ``timestamp``,
    and ``model`` (assistant turns only). Returns the current rolling window
    (up to ``max_turns``); turns that have scrolled out of the window are gone.
    Returns 404 when the session UUID is not found, 503 when the runtime is
    not available.
    """
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    sessions_mgr = getattr(rt, "_sessions", None)
    if sessions_mgr is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    session = next(
        (s for s in sessions_mgr._sessions.values() if s.session_id == session_id),
        None,
    )
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    return {
        "session_id": session_id,
        "channel": session.channel,
        "sender_id": session.sender_id,
        "turn_count": session.turn_count,
        "history": session.history_as_dicts(),
    }


@router.post("/agent/sessions/{session_id}/reset")
async def reset_agent_session(session_id: str) -> dict[str, Any]:
    """Clear the conversation history for one agent session.

    The session itself is kept alive — only its turn history and turn count
    are wiped, identical to the user sending ``/reset`` on that channel.
    Returns 404 if the session UUID is not found.
    """
    rt = _runtime
    if rt is None:
        raise HTTPException(status_code=503, detail="Runtime not available")

    sessions_mgr = getattr(rt, "_sessions", None)
    if sessions_mgr is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    session = next(
        (s for s in sessions_mgr._sessions.values() if s.session_id == session_id),
        None,
    )
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    session.clear()
    return {"session_id": session_id, "reset": True, "turn_count": session.turn_count}


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


@router.post("/channels/add", status_code=201)
async def add_channel(body: dict[str, Any]) -> dict[str, Any]:
    """Append a new channel section to ~/.neuralcleave/config.toml."""
    from pathlib import Path

    channel_type = (body.get("type") or "").strip().lower()
    channel_cfg: dict[str, str] = body.get("config") or {}

    if not channel_type:
        raise HTTPException(status_code=400, detail="'type' is required")

    allowed = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
    if not allowed.match(channel_type):
        raise HTTPException(status_code=400, detail="Invalid channel type name")

    config_path = Path.home() / ".neuralcleave" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"\n[channels.{channel_type}]\n"]
    for key, value in channel_cfg.items():
        if value and re.match(r"^[a-z][a-z0-9_]*$", key):
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"\n')

    with open(config_path, "a", encoding="utf-8") as fh:
        fh.writelines(lines)

    return {"ok": True, "channel_id": channel_type, "written": len(lines) - 1}


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
# Plugins
# ---------------------------------------------------------------------------


@router.get("/plugins")
async def list_plugins() -> dict[str, Any]:
    """List all registered plugins and whether they are currently loaded."""
    pr = _plugin_registry
    if pr is None:
        raise HTTPException(status_code=503, detail="Plugin registry not available")

    plugins = [
        pr.plugin_info(p.metadata.name) or {
            "name": p.metadata.name,
            "loaded": pr.is_loaded(p.metadata.name),
        }
        for p in pr.all_plugins
    ]
    return {"plugins": plugins, "count": len(plugins), "loaded_count": pr.loaded_count}


@router.get("/plugins/{plugin_name}")
async def get_plugin(plugin_name: str) -> dict[str, Any]:
    """Return info for a single plugin. Returns 404 if not registered."""
    pr = _plugin_registry
    if pr is None:
        raise HTTPException(status_code=503, detail="Plugin registry not available")

    info = pr.plugin_info(plugin_name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name!r} not found")
    return info


@router.post("/plugins/reload")
async def reload_all_plugins() -> dict[str, Any]:
    """Hot-reload all registered plugins without restarting the gateway.

    Calls ``on_unload`` on each currently loaded plugin, removes its tools from
    the ToolRegistry, re-imports from entry points (if available), then calls
    ``on_load`` and re-wires tools. Returns the count of successfully reloaded
    plugins.
    """
    pr = _plugin_registry
    if pr is None:
        raise HTTPException(status_code=503, detail="Plugin registry not available")

    total = len(pr.all_plugins)
    reloaded = await pr.reload_all()
    return {"reloaded": reloaded, "total": total, "success": reloaded == total}


@router.post("/plugins/{plugin_name}/reload")
async def reload_plugin(plugin_name: str) -> dict[str, Any]:
    """Hot-reload a single plugin by name.

    Returns 404 if the plugin is not registered. Returns ``{"reloaded": false}``
    if the plugin's ``on_load`` raised an exception (the plugin is left
    unloaded so the registry stays consistent).
    """
    pr = _plugin_registry
    if pr is None:
        raise HTTPException(status_code=503, detail="Plugin registry not available")

    # Check existence before attempting reload
    if pr.plugin_info(plugin_name) is None:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name!r} not found")

    ok = await pr.reload_plugin(plugin_name)
    return {"name": plugin_name, "reloaded": ok}


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

    if "web_search_enabled" in body:
        model_router._web_search = bool(body["web_search_enabled"])
        updated.append("web_search_enabled")

    if not updated:
        raise HTTPException(status_code=422, detail="Provide at least one recognized setting")

    return {"applied": True, "updated_fields": updated}


_VALID_PROVIDERS = {
    "gemini", "anthropic", "openai", "deepseek", "ollama",
    "mistral", "grok", "xai", "cohere", "moonshot", "kimi",
    "glm", "zhipu", "qwen", "alibaba", "ernie", "baidu",
    "doubao", "bytedance",
}


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


# ---------------------------------------------------------------------------
# Voice config
# ---------------------------------------------------------------------------

_VALID_STT_MODELS  = {"tiny", "base", "small", "medium", "large-v3"}
_VALID_TTS_ENGINES = {"pyttsx3", "kokoro", "elevenlabs"}
_VALID_STT_DEVICES = {"cpu", "cuda"}


@router.get("/voice/config")
async def get_voice_config() -> dict[str, Any]:
    """Return the current voice configuration from the live runtime.

    Fields:
    - ``stt_model``:           Active Whisper model size.
    - ``stt_device``:          Inference device (cpu/cuda).
    - ``tts_engine``:          Active TTS engine (pyttsx3/kokoro/elevenlabs).
    - ``elevenlabs_voice_id``: Active ElevenLabs voice ID (empty string if not set).
    - ``language``:            Forced STT language code, or null for auto-detect.
    - ``stt_available``:       Whether STT is initialised in the runtime.
    - ``tts_available``:       Whether TTS is initialised in the runtime.
    """
    rt = get_runtime()
    if rt is None:
        return {
            "stt_model": None, "stt_device": None, "language": None,
            "tts_engine": None, "elevenlabs_voice_id": "",
            "stt_available": False, "tts_available": False,
            "is_handoff_active": False, "wake_handoff_duration_s": 10.0,
        }

    stt = getattr(rt, "_stt", None)
    tts = getattr(rt, "_tts", None)
    cont = getattr(rt, "_continuous", None)

    return {
        "stt_model":            getattr(stt, "model_size", None),
        "stt_device":           getattr(stt, "device",     None),
        "language":             getattr(stt, "language",   None),
        "tts_engine":           getattr(tts, "_active_engine", None),
        "elevenlabs_voice_id":  getattr(tts, "_voice_id",  ""),
        "stt_available":        stt is not None,
        "tts_available":        tts is not None,
        "continuous_listening": getattr(cont, "is_listening", False) if cont is not None else False,
        "vad_backend":          getattr(getattr(cont, "_vad", None), "backend", "energy") if cont is not None else "energy",
        "vad_aggressiveness":   getattr(getattr(cont, "_vad", None), "aggressiveness", 2) if cont is not None else 2,
        "is_handoff_active":    getattr(rt, "_in_handoff", False),
        "wake_handoff_duration_s": getattr(rt, "_wake_handoff_duration_s", 10.0),
    }


@router.patch("/voice/config")
async def patch_voice_config(body: dict[str, Any]) -> dict[str, Any]:
    """Hot-apply voice settings to the running runtime.

    Accepted body keys (all optional):
    - ``tts_engine``:          Switch TTS engine (pyttsx3 | kokoro | elevenlabs).
    - ``elevenlabs_api_key``:  Update ElevenLabs API key on the live TTSEngine.
    - ``elevenlabs_voice_id``: Switch active ElevenLabs voice ID.
    - ``language``:            Override STT language code (null to restore auto).

    STT model and device cannot be hot-swapped — they require a gateway restart
    because faster-whisper loads the model into VRAM/RAM at startup.
    Returns 200 even when the runtime is unavailable — settings are silently
    dropped so the client does not hard-error on startup.
    """
    rt = get_runtime()
    if rt is None:
        return {"applied": False, "updated_fields": []}

    tts = getattr(rt, "_tts", None)
    stt = getattr(rt, "_stt", None)
    updated: list[str] = []

    engine = body.get("tts_engine")
    if engine is not None:
        if engine not in _VALID_TTS_ENGINES:
            raise HTTPException(status_code=422, detail=f"tts_engine must be one of {_VALID_TTS_ENGINES}")
        if tts is not None:
            tts._active_engine = engine
            updated.append("tts_engine")

    api_key = body.get("elevenlabs_api_key")
    if api_key is not None and tts is not None:
        tts._elevenlabs_api_key = api_key
        updated.append("elevenlabs_api_key")

    voice_id = body.get("elevenlabs_voice_id")
    if voice_id is not None and tts is not None:
        tts._voice_id = voice_id
        updated.append("elevenlabs_voice_id")

    if "language" in body and stt is not None:
        stt.language = body["language"]
        updated.append("language")

    cont = getattr(rt, "_continuous", None)
    vad = getattr(cont, "_vad", None) if cont is not None else None

    if "vad_silence_threshold" in body and vad is not None:
        vad.threshold_rms = float(body["vad_silence_threshold"])
        updated.append("vad_silence_threshold")

    if "vad_silence_duration_s" in body and cont is not None:
        cont.set_silence_duration(float(body["vad_silence_duration_s"]))
        updated.append("vad_silence_duration_s")

    if "wake_handoff_duration_s" in body:
        rt.set_wake_handoff_duration(float(body["wake_handoff_duration_s"]))
        updated.append("wake_handoff_duration_s")

    if "ptt_max_duration_s" in body:
        rt.set_ptt_max_duration(float(body["ptt_max_duration_s"]))
        updated.append("ptt_max_duration_s")

    if "input_device" in body:
        rt.set_input_device(body["input_device"] or None)
        updated.append("input_device")

    if "output_device" in body:
        rt.set_output_device(body["output_device"] or None)
        updated.append("output_device")

    return {
        "applied": True,
        "updated_fields": updated,
        "tts_engine": getattr(tts, "_active_engine", None),
        "vad_backend": getattr(vad, "backend", "energy"),
        "vad_silence_threshold": getattr(vad, "threshold_rms", None),
        "input_device": getattr(rt, "_input_device", None),
        "output_device": getattr(rt, "_output_device", None),
    }


_VALID_STT_BACKENDS = {"none", "whisper"}


@router.post("/settings/voice")
async def post_settings_voice(body: dict[str, Any]) -> dict[str, Any]:
    """Write STT backend settings to ~/.neuralcleave/config.toml.

    STT backend, model, and device require a gateway restart to take effect.
    This endpoint persists them to disk so the next restart picks them up.

    Accepted body keys (all optional):
    - ``stt``:        Backend (``"none"`` or ``"whisper"``).
    - ``stt_model``:  Whisper model size (``"tiny"``|``"base"``|``"small"``|``"medium"``|``"large-v3"``).
    - ``stt_device``: Inference device (``"cpu"``|``"cuda"``).
    """
    from pathlib import Path

    stt = body.get("stt")
    stt_model = body.get("stt_model")
    stt_device = body.get("stt_device")

    if stt is not None and stt not in _VALID_STT_BACKENDS:
        raise HTTPException(status_code=422, detail=f"stt must be one of {_VALID_STT_BACKENDS}")
    if stt_model is not None and stt_model not in _VALID_STT_MODELS:
        raise HTTPException(status_code=422, detail=f"stt_model must be one of {_VALID_STT_MODELS}")
    if stt_device is not None and stt_device not in _VALID_STT_DEVICES:
        raise HTTPException(status_code=422, detail=f"stt_device must be one of {_VALID_STT_DEVICES}")

    config_path = Path.home() / ".neuralcleave" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {}
    if config_path.exists():
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        with open(config_path, "rb") as fh:
            raw = tomllib.load(fh)

    voice_section: dict[str, Any] = dict(raw.get("voice", {}))
    if stt is not None:
        voice_section["stt"] = stt
    if stt_model is not None:
        voice_section["stt_model"] = stt_model
    if stt_device is not None:
        voice_section["stt_device"] = stt_device
    raw["voice"] = voice_section

    try:
        import tomli_w
    except ImportError:
        raise HTTPException(status_code=500, detail="tomli_w not installed — cannot write config.toml")

    with open(config_path, "wb") as fh:
        tomli_w.dump(raw, fh)

    updated_fields = [k for k in ("stt", "stt_model", "stt_device") if body.get(k) is not None]
    return {"ok": True, "restart_required": True, "updated_fields": updated_fields}


@router.get("/voice/devices")
async def get_voice_devices() -> dict[str, Any]:
    """Return all enumerable audio input and output devices on the host.

    Uses ``sounddevice.query_devices()`` to list the OS-reported devices.
    Returns empty lists when ``sounddevice`` is not installed or the host
    has no audio hardware.

    Response shape::

        {
            "input":  [{"index": 0, "name": "...", "channels": 2, "sample_rate": 44100.0, "is_default": true}, …],
            "output": [{"index": 1, "name": "...", "channels": 2, "sample_rate": 44100.0, "is_default": false}, …],
            "active": {"input_device": "Built-in Mic", "output_device": null}
        }
    """
    from neuralcleave.voice.device_manager import (
        list_input_devices,
        list_output_devices,
    )

    rt = get_runtime()

    def _fmt(dev: object, *, is_input: bool) -> dict[str, Any]:
        return {
            "index": getattr(dev, "index", -1),
            "name": getattr(dev, "name", ""),
            "channels": (
                getattr(dev, "max_input_channels", 0) if is_input
                else getattr(dev, "max_output_channels", 0)
            ),
            "sample_rate": getattr(dev, "default_sample_rate", 44100.0),
            "is_default": (
                getattr(dev, "is_default_input", False) if is_input
                else getattr(dev, "is_default_output", False)
            ),
        }

    return {
        "input":  [_fmt(d, is_input=True)  for d in list_input_devices()],
        "output": [_fmt(d, is_input=False) for d in list_output_devices()],
        "active": {
            "input_device":  getattr(rt, "_input_device", None),
            "output_device": getattr(rt, "_output_device", None),
        },
    }


@router.get("/voice/status")
async def get_voice_status() -> dict[str, Any]:
    """Return a unified snapshot of all voice subsystem states.

    Combines PTT, continuous listening, wake-word, handoff, STT, and TTS
    availability into a single poll-friendly response.
    """
    rt = get_runtime()
    if rt is None:
        return {
            "runtime_available": False,
            "continuous_listening": False,
            "wake_detector_active": False,
            "is_handoff_active": False,
            "ptt_available": False,
            "ptt_is_recording": False,
            "stt_available": False,
            "tts_available": False,
        }

    cont = getattr(rt, "_continuous", None)
    wake = getattr(rt, "_wake_detector", None)
    ptt = getattr(rt, "_ptt", None)

    return {
        "runtime_available": True,
        # True only when the continuous-listen subsystem is actually configured —
        # distinct from runtime_available so the UI can hide the Listen button
        # when continuous voice is not set up.
        "continuous_available": cont is not None,
        "continuous_listening": getattr(cont, "is_listening", False) if cont is not None else False,
        "wake_detector_active": getattr(wake, "is_detecting", False) if wake is not None else False,
        "is_handoff_active": getattr(rt, "_in_handoff", False),
        "ptt_available": ptt is not None,
        "ptt_is_recording": getattr(ptt, "is_recording", False) if ptt is not None else False,
        "stt_available": getattr(rt, "_stt", None) is not None,
        "tts_available": getattr(rt, "_tts", None) is not None,
    }


@router.post("/voice/calibrate")
async def calibrate_voice(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record ambient noise and auto-tune the VAD silence threshold.

    Optional body key:
    - ``duration_s`` (float, default 1.0): seconds of ambient audio to sample.

    Returns the measured RMS and whether the threshold was updated.
    """
    rt = get_runtime()
    if rt is None:
        return {"calibrated": False, "reason": "runtime not available", "measured_rms": 0.0}

    duration_s = float((body or {}).get("duration_s", 1.0))
    measured_rms = await rt.voice_calibrate(duration_s=duration_s)
    if measured_rms <= 0.0:
        return {
            "calibrated": False,
            "reason": "calibration failed or continuous listener not configured",
            "measured_rms": 0.0,
        }
    return {"calibrated": True, "measured_rms": measured_rms}


@router.post("/voice/session/reset")
async def reset_voice_session() -> dict[str, Any]:
    """Explicitly start a new voice session.

    Rotates the session ID and resets turn count without affecting the
    underlying LLM conversation history.  Useful when the user wants to
    start a new topic and prefers a clean session boundary in metrics/logs.
    Returns ``{"reset": false}`` when the runtime or tracker is not configured.
    """
    rt = get_runtime()
    if rt is None:
        return {"reset": False, "reason": "runtime not available"}

    new_id = rt.voice_session_reset()
    if new_id is None:
        return {"reset": False, "reason": "voice session tracker not configured"}

    return {"reset": True, "session_id": new_id}


@router.get("/voice/session")
async def get_voice_session() -> dict[str, Any]:
    """Return the current voice session state.

    The session tracker records which voice session is active, how many
    utterances have been processed, and how long the session has been idle.
    Returns ``{"available": false}`` when the runtime or tracker is not
    configured.
    """
    rt = get_runtime()
    if rt is None:
        return {"available": False}

    info = rt.get_voice_session_info()
    if info is None:
        return {"available": False}

    return {"available": True, **info}


# ---------------------------------------------------------------------------
# Voice listen (continuous listening)
# ---------------------------------------------------------------------------


@router.get("/voice/listen/status")
async def get_continuous_listen_status() -> dict[str, Any]:
    """Return whether continuous voice listening is currently active."""
    rt = get_runtime()
    cont = getattr(rt, "_continuous", None) if rt is not None else None
    return {
        "continuous_available": cont is not None,
        "continuous_listening": getattr(cont, "is_listening", False) if cont is not None else False,
    }


@router.post("/voice/listen/start")
async def start_continuous_listening() -> dict[str, Any]:
    """Start the always-on continuous voice listener.

    Returns ``{"started": true}`` when listening begins (or was already running).
    Returns ``{"started": false, "reason": "..."}`` when the runtime or the
    ContinuousVoiceListener subsystem is unavailable.
    """
    rt = get_runtime()
    if rt is None:
        return {"started": False, "reason": "runtime not available"}

    cont = getattr(rt, "_continuous", None)
    if cont is None:
        return {"started": False, "reason": "continuous voice not configured"}

    already = bool(getattr(cont, "is_listening", False))
    if not already:
        await cont.start()
    return {"started": True, "already_running": already}


@router.post("/voice/listen/stop")
async def stop_continuous_listening() -> dict[str, Any]:
    """Stop the continuous voice listener.

    Returns ``{"stopped": true}`` when listening halts (or was already stopped).
    Returns ``{"stopped": false, "reason": "..."}`` when unavailable.
    """
    rt = get_runtime()
    if rt is None:
        return {"stopped": False, "reason": "runtime not available"}

    cont = getattr(rt, "_continuous", None)
    if cont is None:
        return {"stopped": False, "reason": "continuous voice not configured"}

    already = not bool(getattr(cont, "is_listening", False))
    if not already:
        await cont.stop()
    return {"stopped": True, "already_stopped": already}


# ---------------------------------------------------------------------------
# Push-to-talk
# ---------------------------------------------------------------------------


@router.post("/voice/ptt/start")
async def start_ptt() -> dict[str, Any]:
    """Start a push-to-talk recording session.

    Returns ``{"started": true}`` when recording begins.
    ``{"started": false, "reason": "..."}`` when unavailable or already active.
    """
    rt = get_runtime()
    if rt is None:
        return {"started": False, "reason": "runtime not available"}
    started = await rt.ptt_start()
    if not started:
        return {"started": False, "reason": "ptt not configured or already recording"}
    return {"started": True}


@router.post("/voice/ptt/stop")
async def stop_ptt() -> dict[str, Any]:
    """Stop PTT recording, run STT + pipeline, play TTS, return the response.

    Fields:
    - ``response``:    Assistant's text reply (empty if nothing was transcribed).
    - ``stopped``:     ``true`` once the recording session ended successfully.
    - ``reason``:      Present only when ``stopped`` is ``false``.
    """
    rt = get_runtime()
    if rt is None:
        return {"stopped": False, "reason": "runtime not available", "response": ""}
    response = await rt.ptt_stop_and_respond()
    return {"stopped": True, "response": response}


@router.get("/voice/ptt/status")
async def get_ptt_status() -> dict[str, Any]:
    """Return current PTT recorder state.

    Fields:
    - ``available``:    Whether a PushToTalkRecorder is configured.
    - ``is_recording``: Whether a recording session is currently active.
    - ``duration_s``:   Elapsed seconds since the session started (0 if idle).
    """
    rt = get_runtime()
    ptt = getattr(rt, "_ptt", None) if rt is not None else None
    return {
        "available": ptt is not None,
        "is_recording": getattr(ptt, "is_recording", False),
        "duration_s": getattr(ptt, "duration_s", 0.0),
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@router.get("/orchestrator/nodes")
async def list_orchestrator_nodes() -> dict:
    """List all registered agent nodes."""
    orch = get_orchestrator()
    if orch is None:
        return {"nodes": []}
    return {"nodes": [n.to_dict() for n in orch.list_nodes()]}


@router.post("/orchestrator/nodes", status_code=201)
async def register_orchestrator_node(body: dict) -> dict:
    """Register a new agent node."""
    from neuralcleave.orchestrator.node import AgentNodeConfig
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    try:
        cfg = AgentNodeConfig(**{k: v for k, v in body.items()})
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    node = orch.register(cfg)
    return {"registered": True, "node": node.config.to_dict()}


@router.get("/orchestrator/nodes/{name}")
async def get_orchestrator_node(name: str) -> dict:
    """Get a single node's config."""
    from neuralcleave.orchestrator.orchestrator import NodeNotFoundError
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    try:
        node = orch.get(name)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
    return node.config.to_dict()


@router.delete("/orchestrator/nodes/{name}", status_code=204)
async def remove_orchestrator_node(name: str) -> None:
    """Remove a node by name."""
    from neuralcleave.orchestrator.orchestrator import NodeNotFoundError
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    try:
        orch.remove(name)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")


@router.patch("/orchestrator/nodes/{name}")
async def patch_orchestrator_node(name: str, body: dict) -> dict:
    """Enable or disable a node."""
    from neuralcleave.orchestrator.orchestrator import NodeNotFoundError
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    try:
        node = orch.get(name)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
    if "enabled" in body:
        node.config.enabled = bool(body["enabled"])
    return {"updated": True, "node": node.config.to_dict()}


@router.post("/orchestrator/route")
async def route_orchestrator_task(body: dict) -> dict:
    """Route a task to the best matching node and return routing info."""
    from neuralcleave.orchestrator.orchestrator import NoEligibleNodeError
    from neuralcleave.orchestrator.task import AgentTask
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    try:
        task = AgentTask(
            content=body.get("content", ""),
            session_id=body.get("session_id", ""),
            task_type=body.get("task_type", "general"),
            source_channel=body.get("source_channel"),
            timeout=float(body.get("timeout", 60.0)),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        result = await orch.route(task)
    except NoEligibleNodeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.to_dict()


@router.get("/orchestrator/status")
async def orchestrator_status() -> dict:
    """Return routing statistics for the orchestrator.

    Includes UI-friendly aliases consumed by the web dashboard:
    - ``total_nodes``: total registered node count (same as ``node_count``)
    - ``enabled_nodes``: count of nodes with ``enabled=True``
    - ``nodes``: full node config dicts (replaces the lightweight stats-only
      list from ``orch.stats()`` so the UI can render priority, task_types, etc.)
    """
    orch = get_orchestrator()
    if orch is None:
        return {
            "available": False,
            "total_routed": 0,
            "node_count": 0,
            "total_nodes": 0,
            "enabled_nodes": 0,
            "nodes": [],
            "namespaces": {},
        }
    stats = orch.stats()
    stats["available"] = True
    # list_nodes() returns AgentNodeConfig objects directly (not AgentNode wrappers)
    node_list = orch.list_nodes()
    # UI aliases — the raw stats() dict uses node_count; web UI reads total_nodes
    stats["total_nodes"] = len(node_list)
    stats["enabled_nodes"] = sum(1 for n in node_list if n.enabled)
    # Replace lightweight stats-only node entries with full config dicts so the
    # web UI can render priority, task_types, memory_namespace, etc.
    stats["nodes"] = [n.to_dict() for n in node_list]
    return stats


@router.get("/orchestrator/nodes/{name}/memory")
async def get_node_memory_namespace(name: str) -> dict:
    """Return the effective memory namespace and stats for a node."""
    from neuralcleave.orchestrator.orchestrator import NodeNotFoundError
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    try:
        node = orch.get(name)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
    ns = node.memory_namespace
    mgr = getattr(orch, "_memory_manager", None)
    ns_stats = mgr.namespace_stats(ns) if mgr else None
    return {
        "node": name,
        "memory_namespace": ns,
        "configured_namespace": node.config.memory_namespace,
        "stats": ns_stats,
    }


@router.delete("/orchestrator/nodes/{name}/memory", status_code=200)
async def clear_node_memory_namespace(name: str) -> dict:
    """Clear all memory entries for a node's namespace."""
    from neuralcleave.orchestrator.orchestrator import NodeNotFoundError
    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    try:
        node = orch.get(name)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
    ns = node.memory_namespace
    mgr = getattr(orch, "_memory_manager", None)
    if mgr is None:
        return {"node": name, "namespace": ns, "cleared": 0, "note": "No memory manager attached"}
    cleared = mgr.clear_namespace(ns)
    return {"node": name, "namespace": ns, "cleared": cleared}


@router.get("/orchestrator/namespaces")
async def list_orchestrator_namespaces() -> dict:
    """List all node→namespace mappings and aggregate memory stats."""
    orch = get_orchestrator()
    if orch is None:
        return {"namespaces": {}, "memory_stats": None}
    ns_map = orch.get_node_namespaces()
    mgr = getattr(orch, "_memory_manager", None)
    mem_stats = mgr.global_stats() if mgr else None
    return {"namespaces": ns_map, "memory_stats": mem_stats}


# ---------------------------------------------------------------------------
# Hub marketplace endpoints  — /api/v1/hub/...
# ---------------------------------------------------------------------------


@router.get("/hub/packages")
async def list_hub_packages() -> dict:
    """List all installed hub packages."""
    installer = get_hub_installer()
    if installer is None:
        return {"available": False, "packages": []}
    packages = installer._registry.list_packages()
    return {"available": True, "packages": [p.to_dict() for p in packages]}


@router.post("/hub/packages", status_code=201)
async def install_hub_package(body: dict) -> dict:
    """Install a skill package from a URL."""
    installer = get_hub_installer()
    if installer is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Hub installer not initialised")
    source_url = body.get("source_url", "")
    if not source_url:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="source_url is required")
    from neuralcleave.hub.installer import InstallError, ScanBlockedError
    try:
        pkg = await installer.install(
            source_url,
            name=body.get("name") or None,
            version=body.get("version", "1.0.0"),
            description=body.get("description", ""),
            author=body.get("author", ""),
            tags=body.get("tags", []),
            force=bool(body.get("force", False)),
        )
        return pkg.to_dict()
    except ScanBlockedError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InstallError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/hub/packages/{name}")
async def get_hub_package(name: str) -> dict:
    """Get metadata for an installed hub package."""
    installer = get_hub_installer()
    if installer is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Hub installer not initialised")
    pkg = installer._registry.get(name)
    if pkg is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Package {name!r} not found")
    return pkg.to_dict()


@router.delete("/hub/packages/{name}", status_code=204)
async def uninstall_hub_package(name: str) -> None:
    """Uninstall a hub package by name."""
    installer = get_hub_installer()
    if installer is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Hub installer not initialised")
    from neuralcleave.hub.installer import InstallError
    try:
        installer.uninstall(name)
    except InstallError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/hub/packages/{name}")
async def patch_hub_package(name: str, body: dict) -> dict:
    """Enable or disable an installed hub package."""
    installer = get_hub_installer()
    if installer is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Hub installer not initialised")
    pkg = installer._registry.get(name)
    if pkg is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Package {name!r} not found")
    if "enabled" in body:
        if body["enabled"]:
            installer._registry.enable(name)
        else:
            installer._registry.disable(name)
    return installer._registry.get(name).to_dict()  # type: ignore[union-attr]


@router.get("/hub/search")
async def search_hub_packages(q: str = "") -> dict:
    """Search installed hub packages by name, description, or tags."""
    installer = get_hub_installer()
    if installer is None:
        return {"available": False, "query": q, "results": []}
    results = installer._registry.search(q)
    return {"available": True, "query": q, "results": [p.to_dict() for p in results]}


@router.post("/hub/scan")
async def scan_hub_url(body: dict) -> dict:
    """Scan a skill URL for safety without installing."""
    installer = get_hub_installer()
    if installer is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Hub installer not initialised")
    source_url = body.get("source_url", "")
    if not source_url:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="source_url is required")
    try:
        code = await installer._fetch_code(source_url)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = installer._scanner.scan_code(code)
    return result.to_dict()


@router.get("/hub/status")
async def hub_status() -> dict:
    """Return hub availability and package count."""
    installer = get_hub_installer()
    if installer is None:
        return {"available": False, "package_count": 0}
    return {
        "available": True,
        "package_count": installer._registry.package_count(),
    }
