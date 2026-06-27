"""Unit tests for cortexflow.gateway.websocket — WebSocketManager + endpoint dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from cortexflow_ai.gateway.routes import set_runtime
from cortexflow_ai.gateway.websocket import (
    Session,
    WebSocketManager,
    get_manager,
    websocket_endpoint,
)
from cortexflow_ai.gateway.websocket import (
    router as ws_router,
)

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


@pytest.mark.asyncio
async def test_manager_start_sets_running():
    m = WebSocketManager()
    await m.start()
    assert m._running is True


@pytest.mark.asyncio
async def test_manager_stop_closes_all_sessions_and_clears():
    m = WebSocketManager()
    ws1 = MagicMock()
    ws1.close = AsyncMock()
    m.add(Session(session_id="s1", websocket=ws1))
    m.add(Session(session_id="s2", websocket=None))  # no websocket — skipped

    await m.stop()

    ws1.close.assert_called_once()
    assert m.session_count == 0
    assert m._running is False


@pytest.mark.asyncio
async def test_manager_stop_swallows_close_errors():
    m = WebSocketManager()
    ws = MagicMock()
    ws.close = AsyncMock(side_effect=RuntimeError("already closed"))
    m.add(Session(session_id="s1", websocket=ws))

    await m.stop()  # must not raise

    assert m.session_count == 0


@pytest.mark.asyncio
async def test_manager_broadcast_sends_to_all_sessions():
    m = WebSocketManager()
    s1 = Session(session_id="s1", websocket=MagicMock())
    s2 = Session(session_id="s2", websocket=MagicMock())
    s1.send = AsyncMock()
    s2.send = AsyncMock()
    m.add(s1)
    m.add(s2)

    await m.broadcast({"type": "notice"})

    s1.send.assert_called_once_with({"type": "notice"})
    s2.send.assert_called_once_with({"type": "notice"})


@pytest.mark.asyncio
async def test_manager_broadcast_filters_by_channel():
    m = WebSocketManager()
    s1 = Session(session_id="s1", channel="general")
    s2 = Session(session_id="s2", channel="other")
    s1.send = AsyncMock()
    s2.send = AsyncMock()
    m.add(s1)
    m.add(s2)

    await m.broadcast({"type": "notice"}, channel="general")

    s1.send.assert_called_once()
    s2.send.assert_not_called()


@pytest.mark.asyncio
async def test_manager_broadcast_no_targets_is_noop():
    m = WebSocketManager()
    await m.broadcast({"type": "notice"}, channel="nobody-here")  # must not raise


# ---------------------------------------------------------------------------
# Session.send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_send_with_no_websocket_is_noop():
    s = Session(session_id="s1", websocket=None)
    await s.send({"type": "x"})  # must not raise


@pytest.mark.asyncio
async def test_session_send_swallows_errors():
    ws = MagicMock()
    ws.send_text = AsyncMock(side_effect=RuntimeError("connection reset"))
    s = Session(session_id="s1", websocket=ws)
    await s.send({"type": "x"})  # must not raise


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


def test_ws_message_runtime_error_returns_error_frame(client):
    class _ExplodingRuntime:
        async def process_inbound_text(self, channel, sender_id, text, *, sender_name="web"):
            raise RuntimeError("model unavailable")

    set_runtime(_ExplodingRuntime())
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "hi", "id": "m9"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["message_id"] == "m9"
        assert "failed" in resp["message"].lower()


# ---------------------------------------------------------------------------
# websocket_endpoint — outer exception handler (non-disconnect errors)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_handles_unexpected_receive_error_gracefully():
    fake_ws = MagicMock()
    fake_ws.accept = AsyncMock()
    fake_ws.send_text = AsyncMock()
    fake_ws.receive_text = AsyncMock(side_effect=RuntimeError("socket broke"))

    manager = get_manager()
    before = manager.session_count

    await websocket_endpoint(fake_ws)  # must not raise

    assert manager.session_count == before


@pytest.mark.asyncio
async def test_endpoint_handles_disconnect_cleanly():
    fake_ws = MagicMock()
    fake_ws.accept = AsyncMock()
    fake_ws.send_text = AsyncMock()
    fake_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

    manager = get_manager()
    before = manager.session_count

    await websocket_endpoint(fake_ws)  # must not raise

    assert manager.session_count == before
