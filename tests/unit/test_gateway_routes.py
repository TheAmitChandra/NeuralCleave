"""Unit tests for cortexflow.gateway.routes — REST API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cortexflow.gateway.main import create_app
from cortexflow.gateway.routes import set_runtime

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_runtime():
    """Ensure each test starts with no injected runtime."""
    set_runtime(None)
    yield
    set_runtime(None)


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=True)


class FakeAdapter:
    channel_id = "telegram"

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

    async def search(self, *, session_id, query, limit=10):
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


class FakeRuntime:
    def __init__(self):
        self._adapters = {"telegram": FakeAdapter()}
        self._long_term = FakeLongTerm()


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


# ---------------------------------------------------------------------------
# PATCH /api/v1/memory/entries/{id}
# ---------------------------------------------------------------------------


def test_edit_memory_entry_no_runtime_503(client):
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


# ---------------------------------------------------------------------------
# DELETE /api/v1/memory/entries/{id}
# ---------------------------------------------------------------------------


def test_delete_memory_entry_no_runtime_503(client):
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
