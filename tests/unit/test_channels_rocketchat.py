"""Unit tests for NeuralCleave.channels.rocketchat — RocketChatAdapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.rocketchat import RocketChatAdapter


def make_adapter(**overrides) -> RocketChatAdapter:
    cfg = {
        "url": "http://localhost:3000",
        "username": "bot",
        "password": "secret",
        "room": "general",
        **overrides,
    }
    return RocketChatAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "rocketchat"
    assert adapter._url == "http://localhost:3000"
    assert adapter._username == "bot"
    assert adapter._room == "general"


def test_url_trailing_slash_stripped():
    adapter = make_adapter(url="http://chat.example.com/")
    assert adapter._url == "http://chat.example.com"


def test_construction_env_resolution(monkeypatch):
    monkeypatch.setenv("RC_BOT_PASS_TEST", "resolved-pass")
    adapter = RocketChatAdapter({"username": "bot", "password": "ENV:RC_BOT_PASS_TEST"})
    assert adapter._password == "resolved-pass"


def test_construction_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("NO_SUCH_RC_PASS", raising=False)
    adapter = RocketChatAdapter({"username": "bot", "password": "ENV:NO_SUCH_RC_PASS"})
    assert adapter._password == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_requires_username_and_password():
    schema = make_adapter().get_config_schema()
    assert "username" in schema["required"]
    assert "password" in schema["required"]


def test_config_schema_default_url():
    schema = make_adapter().get_config_schema()
    assert schema["properties"]["url"]["default"] == "http://localhost:3000"


# ---------------------------------------------------------------------------
# _rest_login — no credentials returns (None, None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rest_login_no_credentials_returns_nones():
    adapter = make_adapter(username="", password="")
    uid, tok = await adapter._rest_login()
    assert uid is None
    assert tok is None


@pytest.mark.asyncio
async def test_rest_login_success_returns_ids():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={
        "data": {"userId": "user-id-123", "authToken": "auth-tok-abc"},
    })

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        uid, tok = await adapter._rest_login()

    assert uid == "user-id-123"
    assert tok == "auth-tok-abc"


@pytest.mark.asyncio
async def test_rest_login_http_error_returns_nones():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("401 Unauthorized"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        uid, tok = await adapter._rest_login()

    assert uid is None
    assert tok is None


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_starts_ws_task(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_rest_login", AsyncMock(return_value=("uid", "tok")))
    monkeypatch.setattr(adapter, "_ws_loop", AsyncMock())

    await adapter.connect()

    assert adapter._bot_user_id == "uid"
    assert adapter._auth_token == "tok"
    assert adapter._ws_task is not None

    await adapter.disconnect()


@pytest.mark.asyncio
async def test_disconnect_with_no_task_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_disconnect_cancels_task_and_closes_ws():
    adapter = make_adapter()

    async def _never():
        await asyncio.sleep(100)

    adapter._ws_task = asyncio.create_task(_never())
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

    await adapter.disconnect()
    assert adapter._ws is None


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_auth_token_returns_none():
    adapter = make_adapter()
    result = await adapter.send("GENERAL", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_success_returns_message_id():
    adapter = make_adapter()
    adapter._auth_token = "tok"
    adapter._bot_user_id = "uid"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"message": {"_id": "msg-123"}})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("GENERAL", "Hello Rocket!")

    assert result == "msg-123"


@pytest.mark.asyncio
async def test_send_http_error_returns_none():
    adapter = make_adapter()
    adapter._auth_token = "tok"
    adapter._bot_user_id = "uid"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("500"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("GENERAL", "hello")

    assert result is None


@pytest.mark.asyncio
async def test_send_includes_room_id_and_text():
    adapter = make_adapter()
    adapter._auth_token = "tok"
    adapter._bot_user_id = "uid"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"message": {"_id": "m1"}})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("ROOM-ID-XYZ", "Test message body")

    call_kwargs = mock_client.post.call_args[1]
    msg = call_kwargs["json"]["message"]
    assert msg["roomId"] == "ROOM-ID-XYZ"
    assert msg["text"] == "Test message body"


@pytest.mark.asyncio
async def test_send_with_reply_to_sets_tmid():
    adapter = make_adapter()
    adapter._auth_token = "tok"
    adapter._bot_user_id = "uid"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"message": {"_id": "m2"}})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("GENERAL", "reply", reply_to="parent-msg-id")

    msg = mock_client.post.call_args[1]["json"]["message"]
    assert msg["tmid"] == "parent-msg-id"


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_success_returns_true():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.ping()

    assert result is True


@pytest.mark.asyncio
async def test_ping_non_200_returns_false():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 503

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.ping()

    assert result is False


@pytest.mark.asyncio
async def test_ping_network_error_returns_false():
    adapter = make_adapter()
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.ping()

    assert result is False


# ---------------------------------------------------------------------------
# _handle_ddp_message — connected → login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ddp_connected_sends_login():
    adapter = make_adapter(username="testbot", password="testpass")
    adapter._auth_token = None

    sent = []

    class FakeWS:
        async def send(self, data):
            sent.append(json.loads(data))

    seq = {"n": 0}

    def next_id():
        seq["n"] += 1
        return str(seq["n"])

    await adapter._handle_ddp_message({"msg": "connected", "session": "s1"}, FakeWS(), next_id)

    assert len(sent) == 1
    msg = sent[0]
    assert msg["msg"] == "method"
    assert msg["method"] == "login"
    params = msg["params"][0]
    assert params["user"]["username"] == "testbot"
    expected_digest = hashlib.sha256(b"testpass").hexdigest()
    assert params["password"]["digest"] == expected_digest
    assert params["password"]["algorithm"] == "sha-256"


# ---------------------------------------------------------------------------
# _handle_ddp_message — result with token → subscribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ddp_result_with_token_subscribes():
    adapter = make_adapter()
    adapter._auth_token = None
    sent = []

    class FakeWS:
        async def send(self, data):
            sent.append(json.loads(data))

    seq = {"n": 0}

    def next_id():
        seq["n"] += 1
        return str(seq["n"])

    result_msg = {
        "msg": "result",
        "id": "1",
        "result": {"token": "new-tok", "id": "user-bot-id"},
    }
    await adapter._handle_ddp_message(result_msg, FakeWS(), next_id)

    assert adapter._auth_token == "new-tok"
    assert adapter._bot_user_id == "user-bot-id"
    assert len(sent) == 1
    sub = sent[0]
    assert sub["msg"] == "sub"
    assert sub["name"] == "stream-room-messages"
    assert sub["params"][0] == "__my_messages__"


# ---------------------------------------------------------------------------
# _handle_ddp_message — result with error logs and returns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ddp_result_with_error_returns_early():
    adapter = make_adapter()
    sent = []

    class FakeWS:
        async def send(self, data):
            sent.append(data)

    def next_id():
        return "1"

    await adapter._handle_ddp_message(
        {"msg": "result", "id": "1", "error": {"error": 403, "message": "Forbidden"}},
        FakeWS(),
        next_id,
    )

    assert sent == []  # no subscribe was sent


# ---------------------------------------------------------------------------
# _handle_ddp_message — ping → pong
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ddp_ping_sends_pong():
    adapter = make_adapter()
    sent = []

    class FakeWS:
        async def send(self, data):
            sent.append(json.loads(data))

    await adapter._handle_ddp_message({"msg": "ping"}, FakeWS(), lambda: "1")

    assert sent == [{"msg": "pong"}]


# ---------------------------------------------------------------------------
# _handle_ddp_message — changed → dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ddp_changed_dispatches_inbound():
    adapter = make_adapter()
    adapter._bot_user_id = "bot-id"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    changed_msg = {
        "msg": "changed",
        "collection": "stream-room-messages",
        "id": "id-1",
        "fields": {
            "eventName": "GENERAL",
            "args": [{
                "_id": "msg-id-1",
                "rid": "GENERAL",
                "u": {"_id": "user-1", "username": "alice", "name": "Alice"},
                "msg": "Hello from Rocket.Chat!",
            }],
        },
    }
    await adapter._handle_ddp_message(changed_msg, None, lambda: "1")
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].text == "Hello from Rocket.Chat!"
    assert dispatched[0].sender_id == "user-1"
    assert dispatched[0].sender_name == "Alice"
    assert dispatched[0].channel == "rocketchat"


# ---------------------------------------------------------------------------
# _process_message_arg — echo guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_message_arg_filters_own_messages():
    adapter = make_adapter()
    adapter._bot_user_id = "bot-id-123"
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    arg = {
        "_id": "msg-1",
        "rid": "GENERAL",
        "u": {"_id": "bot-id-123", "username": "bot", "name": "Bot"},
        "msg": "I said this",
    }
    await adapter._process_message_arg(arg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_process_message_arg_empty_text_skipped():
    adapter = make_adapter()
    adapter._bot_user_id = "other-bot"
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    arg = {
        "_id": "msg-1",
        "rid": "GENERAL",
        "u": {"_id": "user-1", "username": "alice"},
        "msg": "   ",
    }
    await adapter._process_message_arg(arg)
    assert dispatched == []


@pytest.mark.asyncio
async def test_process_message_arg_uses_name_over_username():
    adapter = make_adapter()
    adapter._bot_user_id = "other-bot"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    arg = {
        "_id": "msg-1",
        "rid": "GENERAL",
        "u": {"_id": "user-1", "username": "alice_uname", "name": "Alice Realname"},
        "msg": "hello",
    }
    await adapter._process_message_arg(arg)
    await asyncio.sleep(0)

    assert dispatched[0].sender_name == "Alice Realname"


@pytest.mark.asyncio
async def test_process_message_arg_falls_back_to_username():
    adapter = make_adapter()
    adapter._bot_user_id = "other-bot"
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    arg = {
        "_id": "msg-1",
        "rid": "GENERAL",
        "u": {"_id": "user-1", "username": "bob_uname"},  # no "name"
        "msg": "yo",
    }
    await adapter._process_message_arg(arg)
    await asyncio.sleep(0)

    assert dispatched[0].sender_name == "bob_uname"


# ---------------------------------------------------------------------------
# _ws_connect_and_listen — missing websockets package
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_connect_and_listen_raises_if_websockets_missing():
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "websockets":
            raise ImportError("no websockets")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="websockets package required"):
            await adapter._ws_connect_and_listen("ws://localhost:3000/websocket")


# ---------------------------------------------------------------------------
# _ws_loop — reconnect logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_loop_returns_on_cancelled():
    adapter = make_adapter()
    adapter._ws_connect_and_listen = AsyncMock(side_effect=asyncio.CancelledError())
    await adapter._ws_loop()


@pytest.mark.asyncio
async def test_ws_loop_retries_on_generic_error(monkeypatch):
    adapter = make_adapter()
    call_count = {"n": 0}

    async def fake_connect(ws_url):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("connection refused")
        raise asyncio.CancelledError()

    monkeypatch.setattr(adapter, "_ws_connect_and_listen", fake_connect)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    await adapter._ws_loop()
    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# _rest_headers
# ---------------------------------------------------------------------------


def test_rest_headers_contains_auth_fields():
    adapter = make_adapter()
    adapter._auth_token = "tok-123"
    adapter._bot_user_id = "uid-abc"

    headers = adapter._rest_headers()
    assert headers["X-Auth-Token"] == "tok-123"
    assert headers["X-User-Id"] == "uid-abc"


def test_rest_headers_empty_when_no_auth():
    adapter = make_adapter()
    headers = adapter._rest_headers()
    assert headers["X-Auth-Token"] == ""
    assert headers["X-User-Id"] == ""


# ---------------------------------------------------------------------------
# _handle_ddp_message — unknown msg type is silently ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ddp_unknown_msg_type_is_noop():
    adapter = make_adapter()
    sent = []

    class FakeWS:
        async def send(self, data):
            sent.append(data)

    await adapter._handle_ddp_message({"msg": "added", "collection": "users"}, FakeWS(), lambda: "1")
    assert sent == []  # nothing sent
