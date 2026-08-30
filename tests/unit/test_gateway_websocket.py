"""Unit tests for NeuralCleave.gateway.websocket — WebSocketManager + endpoint dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from neuralcleave.agent.pipeline import PipelineResult, PipelineStreamChunk
from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.gateway.origin_check import set_allowed_origins
from neuralcleave.gateway.routes import set_runtime
from neuralcleave.gateway.websocket import (
    Session,
    WebSocketManager,
    get_manager,
    websocket_endpoint,
)
from neuralcleave.gateway.websocket import (
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
    """Streams *reply* as two chunks (split in half) then a done frame, so
    tests can verify both the chunk and the final-assembly path."""

    def __init__(self, reply: str = "AI reply"):
        self._reply = reply
        self.calls: list[dict] = []

    async def process_inbound_text_stream(self, channel, sender_id, text, *, sender_name="web"):
        self.calls.append({"channel": channel, "sender_id": sender_id, "text": text})
        mid = max(1, len(self._reply) // 2)
        yield PipelineStreamChunk(text=self._reply[:mid])
        yield PipelineStreamChunk(text=self._reply[mid:])
        yield PipelineStreamChunk(
            done=True,
            result=PipelineResult(
                response=self._reply, model="m", provider="p", intent="chat", task_type="general",
            ),
        )


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
        chunk1 = ws.receive_json()
        chunk2 = ws.receive_json()
        done = ws.receive_json()

        assert chunk1["type"] == "message_chunk"
        assert chunk2["type"] == "message_chunk"
        assert chunk1["delta"] + chunk2["delta"] == "Hello from the agent"
        assert chunk1["message_id"] == "m2"

        assert done["type"] == "message_done"
        assert done["text"] == "Hello from the agent"
        assert done["message_id"] == "m2"


def test_ws_empty_message_returns_error(client):
    set_runtime(FakeRuntime())
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "   "})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "empty" in resp["message"].lower()


def test_ws_message_without_client_id_uses_a_random_sender_id(client):
    """Round 7 gap analysis 2 (2026-08-30): without a client_id query param
    (older frontend builds, manual/test clients), sender_id falls back to a
    fresh random ID per connection - identical to the pre-fix behavior. It
    is no longer required to equal the connection's own session_id (a
    separate, deliberately-unrelated field as of this fix)."""
    runtime = FakeRuntime()
    set_runtime(runtime)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "track me", "id": "m3"})
        ws.receive_json()  # chunk 1
        ws.receive_json()  # chunk 2
        ws.receive_json()  # done
    assert runtime.calls[0]["sender_id"]
    assert runtime.calls[0]["channel"] == "websocket"


def test_ws_message_uses_the_client_id_query_param_as_sender_id(client):
    """A client_id query param - generated once by the frontend and
    persisted in localStorage - becomes the durable sender_id, so the same
    real user keeps the same long-term-memory identity across reconnects."""
    runtime = FakeRuntime()
    set_runtime(runtime)
    with client.websocket_connect("/ws?client_id=my-stable-client-id") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "track me", "id": "m3"})
        ws.receive_json()  # chunk 1
        ws.receive_json()  # chunk 2
        ws.receive_json()  # done
    assert runtime.calls[0]["sender_id"] == "my-stable-client-id"


def test_ws_message_ignores_a_malformed_client_id_query_param(client):
    """An invalid client_id (wrong charset, too long) must not flow through
    unsanitized - falls back to a random ID instead."""
    runtime = FakeRuntime()
    set_runtime(runtime)
    with client.websocket_connect("/ws?client_id=not%20valid%3B%20drop%20table") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "track me", "id": "m3"})
        ws.receive_json()  # chunk 1
        ws.receive_json()  # chunk 2
        ws.receive_json()  # done
    assert runtime.calls[0]["sender_id"] != "not valid; drop table"


def test_ws_invalid_json_returns_error(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_text("this is not json{{{")
        resp = ws.receive_json()
        assert resp["type"] == "error"


def test_ws_message_runtime_error_returns_error_frame(client):
    class _ExplodingRuntime:
        async def process_inbound_text_stream(self, channel, sender_id, text, *, sender_name="web"):
            raise RuntimeError("model unavailable")
            yield  # pragma: no cover - makes this an async generator function

    set_runtime(_ExplodingRuntime())
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "hi", "id": "m9"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["message_id"] == "m9"
        assert "failed" in resp["message"].lower()


def test_ws_mid_stream_chunk_error_sends_error_frame_after_partial_chunks(client):
    """Distinct from an outright exception: the runtime's own stream can
    yield a done=True chunk with .error set (e.g. a provider failing after
    already streaming some text) — that must also become an "error" frame,
    not a "message_done" with bogus partial text."""

    class _MidStreamFailureRuntime:
        async def process_inbound_text_stream(self, channel, sender_id, text, *, sender_name="web"):
            yield PipelineStreamChunk(text="partial reply")
            yield PipelineStreamChunk(done=True, error="connection dropped")

    set_runtime(_MidStreamFailureRuntime())
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "hi", "id": "m10"})
        chunk = ws.receive_json()
        err = ws.receive_json()

        assert chunk["type"] == "message_chunk"
        assert chunk["delta"] == "partial reply"

        assert err["type"] == "error"
        assert err["message"] == "connection dropped"
        assert err["message_id"] == "m10"


# ---------------------------------------------------------------------------
# websocket_endpoint — outer exception handler (non-disconnect errors)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_handles_unexpected_receive_error_gracefully():
    fake_ws = MagicMock()
    fake_ws.headers = {}
    fake_ws.query_params = {}
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
    fake_ws.headers = {}
    fake_ws.query_params = {}
    fake_ws.accept = AsyncMock()
    fake_ws.send_text = AsyncMock()
    fake_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

    manager = get_manager()
    before = manager.session_count

    await websocket_endpoint(fake_ws)  # must not raise

    assert manager.session_count == before


def test_ws_providers_exhausted_error_shows_actionable_message(client):
    """When the pipeline raises RuntimeError containing 'providers exhausted',
    the error frame must contain a user-friendly settings hint rather than
    the generic 'Failed to process message'."""

    class _ExhaustedRuntime:
        async def process_inbound_text_stream(self, channel, sender_id, text, *, sender_name="web"):
            raise RuntimeError(
                "All providers exhausted for task_type='cheap_inference'. Last error: GEMINI_API_KEY not set"
            )
            yield  # pragma: no cover

    set_runtime(_ExhaustedRuntime())
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "message", "text": "hi", "id": "m99"})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert resp["message_id"] == "m99"
        assert "settings" in resp["message"].lower() or "provider" in resp["message"].lower()


# ---------------------------------------------------------------------------
# /ws and /ws/voice — origin check
# ---------------------------------------------------------------------------


class TestMainWSOriginCheck:
    """Round 6 gap analysis 5.2 (2026-08-29): CORSMiddleware never applies to
    WebSocket scope, so this handshake-level check is the only real
    protection /ws gets. Mirrors TestTerminalWSOriginCheck."""

    def test_matching_origin_is_accepted(self, client):
        set_allowed_origins(NeuralCleaveConfig())
        with client.websocket_connect("/ws", headers={"origin": "tauri://localhost"}) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "hello"

    def test_mismatched_origin_is_rejected(self, client):
        set_allowed_origins(NeuralCleaveConfig())
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws", headers={"origin": "https://evil.example.com"}
            ) as ws:
                ws.receive_json()

    def test_missing_origin_is_still_accepted(self, client):
        """Preserves existing behavior for non-browser local test clients -
        a real browser always sends Origin for a cross-origin WebSocket
        handshake, so this doesn't weaken the actual protection."""
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "hello"


class TestVoiceWSOriginCheck:
    """Same protection as TestMainWSOriginCheck, applied to /ws/voice. The
    origin check runs before the runtime-availability check, so a rejected
    origin never reaches (and never depends on) get_runtime()."""

    def test_mismatched_origin_is_rejected_before_runtime_check(self, client):
        set_allowed_origins(NeuralCleaveConfig())
        set_runtime(None)  # runtime absent too - origin check must win first
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/ws/voice", headers={"origin": "https://evil.example.com"}
            ) as ws:
                ws.receive_text()
        assert exc_info.value.code == 1008

    def test_missing_origin_falls_through_to_runtime_check(self, client):
        """No origin -> allowed -> proceeds to the pre-existing
        no-runtime-available rejection (code 1011), confirming the origin
        check doesn't short-circuit that behavior."""
        set_runtime(None)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/voice") as ws:
                ws.receive_text()
        assert exc_info.value.code == 1011
