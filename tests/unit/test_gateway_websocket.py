"""Unit tests for cortexflow.gateway.websocket — WebSocketManager + endpoint dispatch."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cortexflow.gateway.websocket import (
    Session,
    WebSocketManager,
    get_manager,
    router as ws_router,
)
from cortexflow.gateway.routes import set_runtime


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_runtime():
    set_runtime(None)
    yield
    set_runtime(None)


@pytest.fixture()
def client():
    # Minimal app with only the WS router — avoids running the full lifespan
    app = FastAPI()
    app.include_router(ws_router)
    return TestClient(app)


class FakeRuntime:
    def __init__(self, reply: str = "AI reply"):
        self._reply = reply
        self.calls: list[dict] = []

    async def process_inbound_text(self, channel, sender_id, text, *, sender_name="web"):
        self.calls.append({"channel": channel, "sender_id": sender_id, "text": text})
        return self._reply


# ---------------------------------------------------------------------------
# WebSocketManager unit tests
# ---------------------------------------------------------------------------


def test_manager_starts_empty():
    m = WebSocketManager()
    assert m.session_count == 0


def test_manager_add_increments_count():
    m = WebSocketManager()
    m.add(Session(session_id="s1"))
    assert m.session_count == 1


def test_manager_remove_decrements_count():
    m = WebSocketManager()
    m.add(Session(session_id="s1"))
    m.remove("s1")
    assert m.session_count == 0


def test_manager_remove_unknown_is_safe():
    m = WebSocketManager()
    m.remove("does-not-exist")  # no raise
    assert m.session_count == 0


def test_get_manager_returns_singleton():
    assert get_manager() is get_manager()


# ---------------------------------------------------------------------------
# WebSocket endpoint — handshake
# ---------------------------------------------------------------------------


def test_ws_sends_hello_on_connect(client):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert "session_id" in hello


def test_ws_ping_pong(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"


def test_ws_subscribe(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "subscribe", "channel": "general"})
        sub = ws.receive_json()
        assert sub["type"] == "subscribed"
        assert sub["channel"] == "general"


def test_ws_unknown_type_returns_error(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "frobnicate"})
        err = ws.receive_json()
        assert err["type"] == "error"


# ---------------------------------------------------------------------------
# WebSocket endpoint — chat message dispatch
# ---------------------------------------------------------------------------


def test_ws_message_without_runtime_returns_error(client):
    set_runtime(None)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "hello", "id": "m1"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "runtime" in resp["message"].lower()


def test_ws_message_with_runtime_returns_reply(client):
    set_runtime(FakeRuntime(reply="Hello from the agent"))
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "hi there", "id": "m2"})
        resp = ws.receive_json()
        assert resp["type"] == "message"
        assert resp["text"] == "Hello from the agent"
        assert resp["message_id"] == "m2"


def test_ws_empty_message_returns_error(client):
    set_runtime(FakeRuntime())
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "   "})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "empty" in resp["message"].lower()


def test_ws_message_passes_session_id_as_sender(client):
    runtime = FakeRuntime()
    set_runtime(runtime)
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        ws.send_json({"type": "message", "text": "track me", "id": "m3"})
        ws.receive_json()
    assert runtime.calls[0]["sender_id"] == hello["session_id"]
    assert runtime.calls[0]["channel"] == "websocket"


def test_ws_invalid_json_returns_error(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_text("this is not json{{{")
        resp = ws.receive_json()
        assert resp["type"] == "error"
