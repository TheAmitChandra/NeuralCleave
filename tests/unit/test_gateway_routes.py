"""Unit tests for cortexflow.gateway.routes — REST API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import cortexflow.gateway.routes as routes_module
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
    async def search(self, *, session_id, query, limit=10):
        return [{"id": "1", "content": "remembered thing", "importance_score": 0.9}]

    async def delete(self, entry_id: str) -> bool:
        return entry_id == "1"


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
