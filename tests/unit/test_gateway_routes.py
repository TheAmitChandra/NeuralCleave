"""Unit tests for cortexflow.gateway.routes — REST API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from cortexflow_ai.agent.session import SessionManager
from cortexflow_ai.gateway.main import create_app
from cortexflow_ai.gateway.routes import get_runtime, set_runtime
from cortexflow_ai.gateway.websocket import Session, get_manager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_runtime():
    """Ensure each test starts with no injected runtime."""
    set_runtime(None)
    yield
    set_runtime(None)


@pytest.fixture(autouse=True)
def reset_sessions():
    """Ensure each test starts with no leftover WebSocket sessions."""
    get_manager()._sessions.clear()
    yield
    get_manager()._sessions.clear()


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=True)


class FakeAdapter:
    channel_id = "telegram"
    is_connected = False

    _ws_task = None
    _runner = None
    _poll_task = None

    async def send(self, target, text, **kwargs):
        return "msg-id-fake"

    def get_config_schema(self):
        return {"type": "object"}


class FakeLongTerm:
    def __init__(self):
        self.deleted: list[int] = []
        self.content_updates: list[tuple[int, str]] = []
        self.importance_updates: list[tuple[int, float]] = []
        self.last_search_session_id: object = "UNSET"

    async def search(self, *, session_id, query, limit=10):
        self.last_search_session_id = session_id
        return [{"id": "1", "content": "remembered thing", "importance_score": 0.9}]

    async def delete_entry(self, entry_id: int) -> bool:
        self.deleted.append(entry_id)
        return entry_id == 1

    async def update_content(self, entry_id: int, content: str) -> bool:
        if entry_id != 1:
            return False
        self.content_updates.append((entry_id, content))
        return True

    async def update_importance(self, entry_id: int, score: float) -> bool:
        if entry_id != 1:
            return False
        self.importance_updates.append((entry_id, score))
        return True

    async def delete_old(self, *, days: int) -> int:
        self.last_delete_old_days = days
        return 5

    async def prune_low_importance(self, *, threshold: float) -> int:
        self.last_prune_threshold = threshold
        return 2


class FakeRuntime:
    def __init__(self):
        self._adapters = {"telegram": FakeAdapter()}
        self._long_term = FakeLongTerm()
        self._unread = {}

    def get_unread_count(self, channel_id: str) -> int:
        return self._unread.get(channel_id, 0)

    def mark_channel_read(self, channel_id: str) -> None:
        self._unread[channel_id] = 0


class FakeRuntimeNoLongTerm:
    def __init__(self):
        self._adapters = {"telegram": FakeAdapter()}
        self._long_term = None


# ---------------------------------------------------------------------------
# GET /api/v1/status
# ---------------------------------------------------------------------------


def test_status_ok(client):
    resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert "active_sessions" in body


def test_status_runtime_not_available(client):
    resp = client.get("/api/v1/status")
    assert resp.json()["runtime_available"] is False


def test_status_runtime_available(client):
    set_runtime(FakeRuntime())
    resp = client.get("/api/v1/status")
    assert resp.json()["runtime_available"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/sessions
# ---------------------------------------------------------------------------


def test_sessions_empty(client):
    resp = client.get("/api/v1/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["sessions"] == []


def test_get_runtime_returns_injected_instance():
    rt = FakeRuntime()
    set_runtime(rt)
    assert get_runtime() is rt


def test_get_runtime_returns_none_by_default():
    assert get_runtime() is None


# ---------------------------------------------------------------------------
# DELETE /api/v1/sessions/{id}
# ---------------------------------------------------------------------------


def test_disconnect_session_not_found_404(client):
    resp = client.delete("/api/v1/sessions/no-such-session")
    assert resp.status_code == 404


def test_disconnect_session_with_websocket_closes_and_removes(client):
    manager = get_manager()
    ws = MagicMock()
    ws.close = AsyncMock()
    manager.add(Session(session_id="ws-sess", websocket=ws))

    resp = client.delete("/api/v1/sessions/ws-sess")

    assert resp.status_code == 204
    ws.close.assert_called_once()
    assert manager._sessions.get("ws-sess") is None


def test_disconnect_session_close_error_is_swallowed(client):
    manager = get_manager()
    ws = MagicMock()
    ws.close = AsyncMock(side_effect=RuntimeError("already closed"))
    manager.add(Session(session_id="bad-close-sess", websocket=ws))

    resp = client.delete("/api/v1/sessions/bad-close-sess")

    assert resp.status_code == 204
    assert manager._sessions.get("bad-close-sess") is None


def test_disconnect_session_without_websocket_just_removes(client):
    manager = get_manager()
    manager.add(Session(session_id="no-ws-sess", websocket=None))

    resp = client.delete("/api/v1/sessions/no-ws-sess")

    assert resp.status_code == 204
    assert manager._sessions.get("no-ws-sess") is None


# ---------------------------------------------------------------------------
# GET /api/v1/agent/sessions
# ---------------------------------------------------------------------------


def test_agent_sessions_no_runtime_503(client):
    resp = client.get("/api/v1/agent/sessions")
    assert resp.status_code == 503


def test_agent_sessions_empty(client):
    rt = FakeRuntime()
    rt._sessions = SessionManager()
    set_runtime(rt)
    resp = client.get("/api/v1/agent/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"] == []
    assert data["count"] == 0


def test_agent_sessions_lists_active_sessions(client):
    rt = FakeRuntime()
    mgr = SessionManager()
    s1 = mgr.get_or_create("telegram", "user-1")
    s1.add_turn("user", "hello")
    mgr.get_or_create("discord", "user-2")
    rt._sessions = mgr
    set_runtime(rt)

    resp = client.get("/api/v1/agent/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    channels = {s["channel"] for s in data["sessions"]}
    assert channels == {"telegram", "discord"}


def test_agent_sessions_exposes_correct_fields(client):
    rt = FakeRuntime()
    mgr = SessionManager()
    s = mgr.get_or_create("telegram", "user-42")
    s.add_turn("user", "test message")
    s.voice_mode = True
    rt._sessions = mgr
    set_runtime(rt)

    resp = client.get("/api/v1/agent/sessions")
    entry = resp.json()["sessions"][0]

    assert entry["channel"] == "telegram"
    assert entry["sender_id"] == "user-42"
    assert entry["turn_count"] == 1
    assert entry["voice_mode"] is True
    assert "session_id" in entry
    assert "idle_seconds" in entry


def test_agent_sessions_no_sessions_attr_returns_empty(client):
    """Runtime without _sessions attribute must return empty list, not 503."""
    rt = FakeRuntime()
    # FakeRuntime has no _sessions by default — getattr should fallback to None
    if hasattr(rt, "_sessions"):
        delattr(rt, "_sessions")
    set_runtime(rt)
    resp = client.get("/api/v1/agent/sessions")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/channels — no runtime
# ---------------------------------------------------------------------------


def test_channels_no_runtime_returns_503(client):
    resp = client.get("/api/v1/channels")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /api/v1/channels — with runtime
# ---------------------------------------------------------------------------


def test_channels_with_runtime(client):
    set_runtime(FakeRuntime())
    resp = client.get("/api/v1/channels")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["channels"][0]["channel_id"] == "telegram"
    assert body["channels"][0]["unread"] == 0


def test_channels_reflects_unread_count(client):
    rt = FakeRuntime()
    rt._unread["telegram"] = 3
    set_runtime(rt)
    resp = client.get("/api/v1/channels")
    assert resp.json()["channels"][0]["unread"] == 3


def test_channels_connected_false_when_no_task(client):
    set_runtime(FakeRuntime())
    resp = client.get("/api/v1/channels")
    assert resp.json()["channels"][0]["connected"] is False


def test_channels_connected_true_via_is_connected(client):
    class FakeConnectedAdapter(FakeAdapter):
        is_connected = True

    rt = FakeRuntime()
    rt._adapters = {"telegram": FakeConnectedAdapter()}
    set_runtime(rt)
    resp = client.get("/api/v1/channels")
    assert resp.json()["channels"][0]["connected"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/channels/{id}
# ---------------------------------------------------------------------------


def test_get_channel_found(client):
    set_runtime(FakeRuntime())
    resp = client.get("/api/v1/channels/telegram")
    assert resp.status_code == 200
    assert resp.json()["channel_id"] == "telegram"


def test_get_channel_not_found(client):
    set_runtime(FakeRuntime())
    resp = client.get("/api/v1/channels/nonexistent")
    assert resp.status_code == 404


def test_get_channel_no_runtime_returns_503(client):
    resp = client.get("/api/v1/channels/telegram")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/v1/channels/{id}/send
# ---------------------------------------------------------------------------


def test_send_via_channel_success(client):
    set_runtime(FakeRuntime())
    resp = client.post(
        "/api/v1/channels/telegram/send",
        json={"target": "chat-123", "text": "Hello!"},
    )
    assert resp.status_code == 200
    assert resp.json()["sent"] is True


def test_send_via_channel_missing_fields(client):
    set_runtime(FakeRuntime())
    resp = client.post(
        "/api/v1/channels/telegram/send",
        json={"target": ""},
    )
    assert resp.status_code == 422


def test_send_via_channel_no_runtime(client):
    resp = client.post(
        "/api/v1/channels/telegram/send",
        json={"target": "t", "text": "hi"},
    )
    assert resp.status_code == 503


def test_send_via_channel_not_found_404(client):
    set_runtime(FakeRuntime())
    resp = client.post(
        "/api/v1/channels/nonexistent/send",
        json={"target": "t", "text": "hi"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/channels/{id}/read
# ---------------------------------------------------------------------------


def test_mark_channel_read_resets_unread(client):
    rt = FakeRuntime()
    rt._unread["telegram"] = 5
    set_runtime(rt)
    resp = client.post("/api/v1/channels/telegram/read")
    assert resp.status_code == 200
    assert resp.json() == {"channel_id": "telegram", "unread": 0}
    assert rt.get_unread_count("telegram") == 0


def test_mark_channel_read_no_runtime_returns_503(client):
    resp = client.post("/api/v1/channels/telegram/read")
    assert resp.status_code == 503


def test_mark_channel_read_not_found_404(client):
    set_runtime(FakeRuntime())
    resp = client.post("/api/v1/channels/nonexistent/read")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/memory/search
# ---------------------------------------------------------------------------


def test_memory_search_no_runtime_503(client):
    resp = client.get("/api/v1/memory/search", params={"q": "cats"})
    assert resp.status_code == 503


def test_memory_search_with_runtime(client):
    set_runtime(FakeRuntime())
    resp = client.get("/api/v1/memory/search", params={"q": "cats"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "cats"
    assert isinstance(body["results"], list)


def test_memory_search_no_long_term_503(client):
    set_runtime(FakeRuntimeNoLongTerm())
    resp = client.get("/api/v1/memory/search", params={"q": "cats"})
    assert resp.status_code == 503


def test_memory_search_passes_none_session_id_when_omitted(client):
    """Regression: session_id defaulted to '%' which was used as a literal
    SQL value, so WHERE session_id = '%' never matched real sessions and
    always returned empty results."""
    rt = FakeRuntime()
    set_runtime(rt)
    client.get("/api/v1/memory/search", params={"q": "cats"})
    assert rt._long_term.last_search_session_id is None


def test_memory_search_passes_explicit_session_id_when_provided(client):
    rt = FakeRuntime()
    set_runtime(rt)
    client.get("/api/v1/memory/search", params={"q": "cats", "session_id": "sess-abc"})
    assert rt._long_term.last_search_session_id == "sess-abc"


# ---------------------------------------------------------------------------
# GET /api/v1/memory/entries
# ---------------------------------------------------------------------------


def test_list_memory_entries_no_runtime_503(client):
    resp = client.get("/api/v1/memory/entries")
    assert resp.status_code == 503


def test_list_memory_entries_with_runtime(client):
    set_runtime(FakeRuntime())
    resp = client.get("/api/v1/memory/entries")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["entries"], list)
    assert body["count"] == len(body["entries"])


def test_list_memory_entries_no_long_term_503(client):
    set_runtime(FakeRuntimeNoLongTerm())
    resp = client.get("/api/v1/memory/entries")
    assert resp.status_code == 503


def test_list_memory_entries_passes_none_session_id_when_omitted(client):
    """Regression: same '%' session_id bug as memory/search."""
    rt = FakeRuntime()
    set_runtime(rt)
    client.get("/api/v1/memory/entries")
    assert rt._long_term.last_search_session_id is None


# ---------------------------------------------------------------------------
# PATCH /api/v1/memory/entries/{id}
# ---------------------------------------------------------------------------


def test_edit_memory_entry_no_runtime_503(client):
    resp = client.patch("/api/v1/memory/entries/1", json={"content": "x"})
    assert resp.status_code == 503


def test_edit_memory_entry_no_long_term_503(client):
    set_runtime(FakeRuntimeNoLongTerm())
    resp = client.patch("/api/v1/memory/entries/1", json={"content": "x"})
    assert resp.status_code == 503


def test_edit_memory_entry_content(client):
    rt = FakeRuntime()
    set_runtime(rt)
    resp = client.patch("/api/v1/memory/entries/1", json={"content": "edited"})
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "updated": True}
    assert rt._long_term.content_updates == [(1, "edited")]


def test_edit_memory_entry_importance(client):
    rt = FakeRuntime()
    set_runtime(rt)
    resp = client.patch("/api/v1/memory/entries/1", json={"importance": 0.9})
    assert resp.status_code == 200
    assert rt._long_term.importance_updates == [(1, 0.9)]


def test_edit_memory_entry_both_fields(client):
    rt = FakeRuntime()
    set_runtime(rt)
    resp = client.patch("/api/v1/memory/entries/1", json={"content": "edited", "importance": 0.7})
    assert resp.status_code == 200
    assert rt._long_term.content_updates == [(1, "edited")]
    assert rt._long_term.importance_updates == [(1, 0.7)]


def test_edit_memory_entry_no_fields_422(client):
    set_runtime(FakeRuntime())
    resp = client.patch("/api/v1/memory/entries/1", json={})
    assert resp.status_code == 422


def test_edit_memory_entry_non_integer_id_422(client):
    set_runtime(FakeRuntime())
    resp = client.patch("/api/v1/memory/entries/not-a-number", json={"content": "x"})
    assert resp.status_code == 422


def test_edit_memory_entry_missing_id_404(client):
    set_runtime(FakeRuntime())
    resp = client.patch("/api/v1/memory/entries/99999", json={"content": "x"})
    assert resp.status_code == 404


class FakeLongTermPartialFail:
    """update_content succeeds for id=1 but update_importance always fails."""

    def __init__(self):
        self.content_updates: list = []
        self.importance_updates: list = []

    async def search(self, *, session_id, query, limit=10):
        return []

    async def update_content(self, entry_id: int, content: str) -> bool:
        if entry_id != 1:
            return False
        self.content_updates.append((entry_id, content))
        return True

    async def update_importance(self, entry_id: int, score: float) -> bool:
        self.importance_updates.append((entry_id, score))
        return False  # always "not found" for importance

    async def delete_entry(self, entry_id: int) -> bool:
        return False


class FakeRuntimePartialFail:
    def __init__(self):
        self._adapters = {}
        self._long_term = FakeLongTermPartialFail()


def test_edit_memory_entry_partial_fail_still_returns_200(client):
    """If content update succeeds but importance update fails, any() → 200."""
    set_runtime(FakeRuntimePartialFail())
    resp = client.patch("/api/v1/memory/entries/1", json={"content": "ok", "importance": 0.5})
    assert resp.status_code == 200


def test_edit_memory_entry_all_fail_returns_404(client):
    """If ALL update calls return False, the entry is not found → 404."""
    set_runtime(FakeRuntimePartialFail())
    # entry_id=99 → update_content returns False, update_importance returns False
    resp = client.patch("/api/v1/memory/entries/99", json={"content": "x", "importance": 0.5})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/memory/entries/{id}
# ---------------------------------------------------------------------------


def test_delete_memory_entry_no_runtime_503(client):
    resp = client.delete("/api/v1/memory/entries/1")
    assert resp.status_code == 503


def test_delete_memory_entry_no_long_term_503(client):
    set_runtime(FakeRuntimeNoLongTerm())
    resp = client.delete("/api/v1/memory/entries/1")
    assert resp.status_code == 503


def test_delete_memory_entry_success(client):
    rt = FakeRuntime()
    set_runtime(rt)
    resp = client.delete("/api/v1/memory/entries/1")
    assert resp.status_code == 204
    assert rt._long_term.deleted == [1]


def test_delete_memory_entry_missing_404(client):
    set_runtime(FakeRuntime())
    resp = client.delete("/api/v1/memory/entries/99999")
    assert resp.status_code == 404


def test_delete_memory_entry_non_integer_id_422(client):
    set_runtime(FakeRuntime())
    resp = client.delete("/api/v1/memory/entries/not-a-number")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/memory/prune
# ---------------------------------------------------------------------------


def test_prune_memory_no_runtime_503(client):
    resp = client.post("/api/v1/memory/prune")
    assert resp.status_code == 503


def test_prune_memory_no_long_term_503(client):
    rt = FakeRuntime()
    rt._long_term = None
    set_runtime(rt)
    resp = client.post("/api/v1/memory/prune")
    assert resp.status_code == 503


def test_prune_memory_default_params(client):
    set_runtime(FakeRuntime())
    resp = client.post("/api/v1/memory/prune")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pruned"] is True
    assert data["stale_removed"] == 5
    assert data["low_importance_removed"] == 2
    assert data["total_removed"] == 7


def test_prune_memory_custom_params(client):
    rt = FakeRuntime()
    set_runtime(rt)
    resp = client.post("/api/v1/memory/prune", json={"days": 30, "threshold": 0.3})
    assert resp.status_code == 200
    assert rt._long_term.last_delete_old_days == 30
    assert rt._long_term.last_prune_threshold == 0.3


def test_prune_memory_returns_zero_when_nothing_removed(client):
    from unittest.mock import AsyncMock
    rt = FakeRuntime()
    rt._long_term.delete_old = AsyncMock(return_value=0)
    rt._long_term.prune_low_importance = AsyncMock(return_value=0)
    set_runtime(rt)
    resp = client.post("/api/v1/memory/prune")
    assert resp.status_code == 200
    assert resp.json()["total_removed"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/metrics
# ---------------------------------------------------------------------------


def test_metrics_prometheus_format(client):
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert "messages_total" in resp.text
    assert "# TYPE" in resp.text


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/snapshot
# ---------------------------------------------------------------------------


def test_metrics_snapshot_json(client):
    resp = client.get("/api/v1/metrics/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert "messages_total" in body
    assert body["messages_total"]["type"] == "counter"


# ---------------------------------------------------------------------------
# GET /health (from main.py — not api/v1 but tested here for completeness)
# ---------------------------------------------------------------------------


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/v1/settings/llm
# ---------------------------------------------------------------------------


class FakeModelRouter:
    def __init__(self):
        self._gemini_key = ""
        self._deepseek_key = ""
        self._anthropic_key = ""
        self._openai_key = ""
        self._ollama_url = "http://localhost:11434"


class FakePipeline:
    def __init__(self):
        self._router = FakeModelRouter()


class FakeRuntimeWithRouter:
    def __init__(self):
        self._adapters = {}
        self._long_term = None
        self._pipeline = FakePipeline()

    def get_unread_count(self, channel_id: str) -> int:
        return 0

    def mark_channel_read(self, channel_id: str) -> None:
        pass


class FakeRuntimeNoPipeline:
    def __init__(self):
        self._adapters = {}
        self._long_term = None
        self._pipeline = None


def test_apply_llm_settings_no_runtime_503(client):
    resp = client.post("/api/v1/settings/llm", json={"gemini_api_key": "k"})
    assert resp.status_code == 503


def test_apply_llm_settings_no_pipeline_503(client):
    set_runtime(FakeRuntimeNoPipeline())
    resp = client.post("/api/v1/settings/llm", json={"gemini_api_key": "k"})
    assert resp.status_code == 503


def test_apply_llm_settings_empty_body_422(client):
    set_runtime(FakeRuntimeWithRouter())
    resp = client.post("/api/v1/settings/llm", json={})
    assert resp.status_code == 422


def test_apply_llm_settings_patches_gemini_key(client):
    rt = FakeRuntimeWithRouter()
    set_runtime(rt)
    resp = client.post("/api/v1/settings/llm", json={"gemini_api_key": "test-gemini-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert "gemini_api_key" in body["updated_fields"]
    assert rt._pipeline._router._gemini_key == "test-gemini-key"


def test_apply_llm_settings_patches_multiple_fields(client):
    rt = FakeRuntimeWithRouter()
    set_runtime(rt)
    resp = client.post(
        "/api/v1/settings/llm",
        json={
            "deepseek_api_key": "ds-key",
            "ollama_base_url": "http://myhost:11434",
        },
    )
    assert resp.status_code == 200
    assert rt._pipeline._router._deepseek_key == "ds-key"
    assert rt._pipeline._router._ollama_url == "http://myhost:11434"
    assert set(resp.json()["updated_fields"]) == {"deepseek_api_key", "ollama_base_url"}


def test_apply_llm_settings_ignores_unknown_keys(client):
    rt = FakeRuntimeWithRouter()
    set_runtime(rt)
    resp = client.post(
        "/api/v1/settings/llm",
        json={"gemini_api_key": "gk", "unknown_field": "ignored"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated_fields"] == ["gemini_api_key"]


def test_apply_llm_settings_empty_string_alone_returns_422(client):
    """An empty string must not count as 'provided' — body is effectively empty."""
    set_runtime(FakeRuntimeWithRouter())
    resp = client.post("/api/v1/settings/llm", json={"gemini_api_key": ""})
    assert resp.status_code == 422


def test_apply_llm_settings_empty_string_does_not_overwrite_existing_key(client):
    """Sending an empty string for a key that already has a value must leave it unchanged."""
    rt = FakeRuntimeWithRouter()
    rt._pipeline._router._gemini_key = "pre-set-key"
    set_runtime(rt)
    client.post("/api/v1/settings/llm", json={"gemini_api_key": ""})
    assert rt._pipeline._router._gemini_key == "pre-set-key"


def test_apply_llm_settings_empty_string_skipped_valid_key_still_applied(client):
    """If a body mixes an empty string with a valid value, only the valid one is applied."""
    rt = FakeRuntimeWithRouter()
    set_runtime(rt)
    resp = client.post(
        "/api/v1/settings/llm",
        json={"gemini_api_key": "", "deepseek_api_key": "valid-ds-key"},
    )
    assert resp.status_code == 200
    assert rt._pipeline._router._gemini_key == ""  # unchanged (was empty, stays empty)
    assert rt._pipeline._router._deepseek_key == "valid-ds-key"
    assert resp.json()["updated_fields"] == ["deepseek_api_key"]


# ---------------------------------------------------------------------------
# POST /api/v1/settings/model
# ---------------------------------------------------------------------------


class FakeModelRouterFull(FakeModelRouter):
    """Extends FakeModelRouter with the new model-settings fields."""

    def __init__(self):
        super().__init__()
        self._forced_provider: str | None = None
        self.privacy_mode: bool = False


class FakeRuntimeWithFullRouter(FakeRuntimeWithRouter):
    def __init__(self):
        super().__init__()
        self._pipeline = type("_P", (), {"_router": FakeModelRouterFull()})()


def test_apply_model_settings_no_runtime_503(client):
    resp = client.post("/api/v1/settings/model", json={"provider": "gemini"})
    assert resp.status_code == 503


def test_apply_model_settings_no_pipeline_503(client):
    set_runtime(FakeRuntimeNoPipeline())
    resp = client.post("/api/v1/settings/model", json={"provider": "gemini"})
    assert resp.status_code == 503


def test_apply_model_settings_empty_body_422(client):
    set_runtime(FakeRuntimeWithFullRouter())
    resp = client.post("/api/v1/settings/model", json={})
    assert resp.status_code == 422


def test_apply_model_settings_invalid_provider_422(client):
    set_runtime(FakeRuntimeWithFullRouter())
    resp = client.post("/api/v1/settings/model", json={"provider": "grok"})
    assert resp.status_code == 422


def test_apply_model_settings_set_provider(client):
    rt = FakeRuntimeWithFullRouter()
    set_runtime(rt)
    resp = client.post("/api/v1/settings/model", json={"provider": "anthropic"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["settings"]["provider"] == "anthropic"
    assert rt._pipeline._router._forced_provider == "anthropic"


def test_apply_model_settings_clear_provider_with_null(client):
    rt = FakeRuntimeWithFullRouter()
    rt._pipeline._router._forced_provider = "gemini"
    set_runtime(rt)
    resp = client.post("/api/v1/settings/model", json={"provider": None})
    assert resp.status_code == 200
    assert rt._pipeline._router._forced_provider is None
    assert resp.json()["settings"]["provider"] is None


def test_apply_model_settings_set_privacy_mode(client):
    rt = FakeRuntimeWithFullRouter()
    set_runtime(rt)
    resp = client.post("/api/v1/settings/model", json={"privacy_mode": True})
    assert resp.status_code == 200
    assert rt._pipeline._router.privacy_mode is True
    assert resp.json()["settings"]["privacy_mode"] is True


def test_apply_model_settings_privacy_mode_non_bool_422(client):
    set_runtime(FakeRuntimeWithFullRouter())
    resp = client.post("/api/v1/settings/model", json={"privacy_mode": "yes"})
    assert resp.status_code == 422


def test_apply_model_settings_all_valid_providers(client):
    """Every provider name in the UI must be accepted."""
    valid = ["gemini", "anthropic", "openai", "deepseek", "ollama"]
    for provider in valid:
        rt = FakeRuntimeWithFullRouter()
        set_runtime(rt)
        resp = client.post("/api/v1/settings/model", json={"provider": provider})
        assert resp.status_code == 200, f"provider={provider!r} returned {resp.status_code}"
        assert rt._pipeline._router._forced_provider == provider
