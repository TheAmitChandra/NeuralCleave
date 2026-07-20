"""Unit tests for NeuralCleave.channels.mattermost — MattermostAdapter."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.mattermost import MattermostAdapter


def make_adapter(**overrides) -> MattermostAdapter:
    cfg = {
        "url": "http://localhost:8065",
        "token": "test-token-xyz",
        "channel": "town-square",
        **overrides,
    }
    return MattermostAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "mattermost"
    assert adapter._url == "http://localhost:8065"
    assert adapter._channel_name == "town-square"


def test_url_trailing_slash_stripped():
    adapter = make_adapter(url="http://mattermost.example.com/")
    assert adapter._url == "http://mattermost.example.com"


def test_construction_env_resolution(monkeypatch):
    monkeypatch.setenv("MM_TOKEN_TEST", "resolved-token")
    adapter = MattermostAdapter({"token": "ENV:MM_TOKEN_TEST"})
    assert adapter._token == "resolved-token"


def test_construction_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("MM_NO_SUCH_TOKEN", raising=False)
    adapter = MattermostAdapter({"token": "ENV:MM_NO_SUCH_TOKEN"})
    assert adapter._token == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_requires_token():
    schema = make_adapter().get_config_schema()
    assert "token" in schema["required"]


# ---------------------------------------------------------------------------
# send — no token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_token_returns_none():
    adapter = make_adapter(token="")
    result = await adapter.send("channel-id-123", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# send — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_success_returns_post_id():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"id": "post-xyz-789"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("channel-123", "Hello Mattermost!")

    assert result == "post-xyz-789"


# ---------------------------------------------------------------------------
# send — HTTP error returns None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_http_error_returns_none():
    adapter = make_adapter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("503 Service Unavailable"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("channel-123", "hello")

    assert result is None


# ---------------------------------------------------------------------------
# _fetch_bot_user_id — no token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_bot_user_id_no_token_returns_none():
    adapter = make_adapter(token="")
    result = await adapter._fetch_bot_user_id()
    assert result is None


# ---------------------------------------------------------------------------
# _process_event — non-posted event is ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_ignores_non_posted():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    await adapter._process_event({"event": "user_added", "data": {}})
    assert len(dispatched) == 0


# ---------------------------------------------------------------------------
# _process_event — own message is filtered out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_filters_own_messages():
    adapter = make_adapter()
    adapter._bot_user_id = "bot-user-id"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    post = {"user_id": "bot-user-id", "channel_id": "ch1", "message": "I said this"}
    await adapter._process_event({"event": "posted", "data": {"post": json.dumps(post)}})
    assert len(dispatched) == 0


# ---------------------------------------------------------------------------
# _process_event — valid message is dispatched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_dispatches_inbound_message():
    adapter = make_adapter()
    adapter._bot_user_id = "bot-user-id"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    post = {
        "user_id": "alice",
        "channel_id": "ch1",
        "message": "Hey bot, what's up?",
    }
    event = {
        "event": "posted",
        "data": {
            "post": json.dumps(post),
            "sender_name": "@alice",
        },
    }
    await adapter._process_event(event)
    await asyncio.sleep(0)  # let create_task run

    assert len(dispatched) == 1
    assert dispatched[0].text == "Hey bot, what's up?"
    assert dispatched[0].sender_id == "alice"
    assert dispatched[0].sender_name == "alice"


# ---------------------------------------------------------------------------
# _process_event — malformed / empty payloads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_malformed_json_post_returns_early():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = lambda msg: dispatched.append(msg)

    await adapter._process_event({"event": "posted", "data": {"post": "not-valid-json{"}})

    assert dispatched == []


@pytest.mark.asyncio
async def test_process_event_empty_message_text_skipped():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = lambda msg: dispatched.append(msg)

    post = {"user_id": "alice", "channel_id": "ch1", "message": "   "}
    await adapter._process_event({"event": "posted", "data": {"post": json.dumps(post)}})

    assert dispatched == []


@pytest.mark.asyncio
async def test_process_event_post_already_dict_not_string():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    post = {"user_id": "alice", "channel_id": "ch1", "message": "hi there"}
    await adapter._process_event({"event": "posted", "data": {"post": post}})
    await asyncio.sleep(0)

    assert len(dispatched) == 1


# ---------------------------------------------------------------------------
# _fetch_bot_user_id — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_bot_user_id_success():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"id": "bot-user-id"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter._fetch_bot_user_id()

    assert result == "bot-user-id"


@pytest.mark.asyncio
async def test_fetch_bot_user_id_http_error_returns_none():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("401"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter._fetch_bot_user_id()

    assert result is None


# ---------------------------------------------------------------------------
# send() — reply_to
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_with_reply_to_sets_root_id():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"id": "post-2"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("channel-123", "a reply", reply_to="post-original")

    sent_payload = mock_client.post.call_args[1]["json"]
    assert sent_payload["root_id"] == "post-original"


# ---------------------------------------------------------------------------
# connect() / disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_sets_bot_user_id_and_starts_ws_task(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_fetch_bot_user_id", AsyncMock(return_value="bot-id"))
    monkeypatch.setattr(adapter, "_ws_loop", AsyncMock())

    await adapter.connect()

    assert adapter._bot_user_id == "bot-id"
    assert adapter._ws_task is not None

    await adapter.disconnect()


@pytest.mark.asyncio
async def test_disconnect_with_no_task_or_ws_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise


@pytest.mark.asyncio
async def test_disconnect_cancels_ws_task_and_closes_ws(monkeypatch):
    adapter = make_adapter()

    async def _never_ending():
        await asyncio.sleep(100)

    adapter._ws_task = asyncio.create_task(_never_ending())
    mock_ws = MagicMock()
    mock_ws.close = AsyncMock()
    adapter._ws = mock_ws

    await adapter.disconnect()

    assert adapter._ws_task is None
    assert adapter._ws is None
    mock_ws.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_swallows_ws_close_exception():
    adapter = make_adapter()
    mock_ws = MagicMock()
    mock_ws.close = AsyncMock(side_effect=Exception("already closed"))
    adapter._ws = mock_ws

    await adapter.disconnect()  # should not raise

    assert adapter._ws is None


# ---------------------------------------------------------------------------
# _ws_connect_and_listen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_connect_and_listen_raises_if_websockets_not_installed():
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "websockets":
            raise ImportError("No module named 'websockets'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="websockets package required"):
            await adapter._ws_connect_and_listen("ws://localhost:8065/api/v4/websocket")


class _FakeWebSocket:
    def __init__(self, incoming: list[str]) -> None:
        self._incoming = incoming
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for item in self._incoming:
            yield item


class _FakeWSConnectCtx:
    def __init__(self, ws: _FakeWebSocket) -> None:
        self._ws = ws

    async def __aenter__(self):
        return self._ws

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_ws_connect_and_listen_processes_messages():
    adapter = make_adapter()
    processed = []

    async def fake_process_event(event):
        processed.append(event)

    adapter._process_event = fake_process_event

    fake_ws = _FakeWebSocket([json.dumps({"event": "posted", "data": {}})])
    mock_websockets = MagicMock()
    mock_websockets.connect = MagicMock(return_value=_FakeWSConnectCtx(fake_ws))

    with patch.dict("sys.modules", {"websockets": mock_websockets}):
        await adapter._ws_connect_and_listen("ws://localhost:8065/api/v4/websocket")

    assert len(processed) == 1
    assert adapter._ws is fake_ws
    assert len(fake_ws.sent) == 1  # authentication_challenge was sent


# ---------------------------------------------------------------------------
# _ws_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_loop_returns_on_cancelled_error(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_ws_connect_and_listen", AsyncMock(side_effect=asyncio.CancelledError()))

    await adapter._ws_loop()  # should return cleanly


@pytest.mark.asyncio
async def test_ws_loop_retries_after_generic_exception(monkeypatch):
    adapter = make_adapter()
    call_count = {"n": 0}

    async def fake_connect_and_listen(ws_url):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("connection refused")
        raise asyncio.CancelledError()

    monkeypatch.setattr(adapter, "_ws_connect_and_listen", fake_connect_and_listen)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await adapter._ws_loop()

    assert call_count["n"] == 2
