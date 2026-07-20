"""Unit tests for neuralcleave.channels.qq_bot — QQBotAdapter.

Covers:
  - Constructor / defaults / config parsing
  - is_connected lifecycle
  - connect() / disconnect()
  - _verify_signature() — valid, invalid, no secret dev mode, HMAC-SHA256
  - _make_challenge_response() — correct HMAC over event_ts + plain_token
  - _get_access_token() — cache hit, refresh, expiry buffer, missing creds, error
  - _extract_message() — all four event types, mention stripping
  - _parse_target() — all prefix forms + bare string
  - _handle_webhook() — challenge op=13, all message types, sig check, echo guard,
      empty text, unknown events, JSON error
  - _handle_health() — GET returns 200
  - send() — all target formats, success, no target, no token, HTTP error, network error
  - ping() — 200 valid, no creds, token error, network error
  - get_config_schema() — shape and required fields
  - Constants
  - _strip_mentions() — strips <@!id> and <@id> tags
  - Edge / integration cases
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.qq_bot import (
    _APPTOKEN_URL,
    _GROUP_API,
    _GUILD_API,
    _OP_CHALLENGE,
    QQBotAdapter,
    _strip_mentions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides: Any) -> QQBotAdapter:
    cfg: dict[str, Any] = {
        "app_id": "12345678",
        "client_secret": "mysecret",
        **overrides,
    }
    return QQBotAdapter(cfg)


def _hmac_sig(secret: str, timestamp: str, body: bytes) -> str:
    msg = timestamp.encode() + body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _make_request(body: dict, secret: str = "mysecret", ts: str = "1700000000") -> MagicMock:
    raw = json.dumps(body).encode()
    sig = _hmac_sig(secret, ts, raw) if secret else ""
    req = MagicMock()
    req.headers = {
        "X-Signature-Ed25519": sig,
        "X-Signature-Timestamp": ts,
    }
    req.read = AsyncMock(return_value=raw)
    return req


def _msg_event(
    event_type: str = "AT_MESSAGE_CREATE",
    content: str = "hello",
    author_id: str = "user123",
    channel_id: str = "chan001",
    guild_id: str = "guild001",
    group_openid: str = "grp001",
    user_openid: str = "user_open_001",
    member_openid: str = "member_open_001",
    msg_id: str = "msg001",
    ts: str = "2023-10-01T12:00:00+08:00",
) -> dict:
    if event_type == "AT_MESSAGE_CREATE":
        author = {"id": author_id, "username": "Alice"}
        data = {
            "id": msg_id,
            "content": content,
            "author": author,
            "channel_id": channel_id,
            "guild_id": guild_id,
            "timestamp": ts,
        }
    elif event_type == "DIRECT_MESSAGE_CREATE":
        author = {"id": author_id, "username": "Alice"}
        data = {
            "id": msg_id,
            "content": content,
            "author": author,
            "guild_id": guild_id,
            "timestamp": ts,
        }
    elif event_type == "C2C_MESSAGE_CREATE":
        author = {"user_openid": user_openid}
        data = {"id": msg_id, "content": content, "author": author, "timestamp": ts}
    elif event_type == "GROUP_AT_MESSAGE_CREATE":
        author = {"member_openid": member_openid}
        data = {
            "id": msg_id,
            "content": content,
            "author": author,
            "group_openid": group_openid,
            "timestamp": ts,
        }
    else:
        data = {"id": msg_id, "content": content, "author": {}, "timestamp": ts}

    return {"op": 0, "t": event_type, "s": 1, "d": data}


def fake_token_response(token: str = "newtoken", expires: str = "7200") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"access_token": token, "expires_in": expires})
    return resp


def fake_send_response(status: int = 200, msg_id: str = "sent001") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = json.dumps({"id": msg_id})
    resp.json = MagicMock(return_value={"id": msg_id})
    return resp


def fake_http_client(**method_responses: MagicMock) -> MagicMock:
    client = AsyncMock()
    for method, resp in method_responses.items():
        setattr(client, method, AsyncMock(return_value=resp))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ===========================================================================
# 1. _strip_mentions()
# ===========================================================================


class TestStripMentions:
    def test_strips_at_bang_mention(self):
        assert _strip_mentions("<@!12345> hello") == "hello"

    def test_strips_at_mention(self):
        assert _strip_mentions("<@12345> hello") == "hello"

    def test_strips_multiple_mentions(self):
        assert _strip_mentions("<@!1> <@!2> hi there") == "hi there"

    def test_no_mention_unchanged(self):
        assert _strip_mentions("just text") == "just text"

    def test_empty_string(self):
        assert _strip_mentions("") == ""

    def test_only_mention_gives_empty(self):
        assert _strip_mentions("<@!12345>") == ""

    def test_strips_and_trims_whitespace(self):
        assert _strip_mentions("  <@!12345>  hello  ") == "hello"


# ===========================================================================
# 2. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_app_id_empty(self):
        assert QQBotAdapter({})._app_id == ""

    def test_default_client_secret_empty(self):
        assert QQBotAdapter({})._client_secret == ""

    def test_default_bot_openid_empty(self):
        assert QQBotAdapter({})._bot_openid == ""

    def test_default_host(self):
        assert make_adapter()._host == "0.0.0.0"

    def test_default_port(self):
        assert make_adapter()._port == 8093

    def test_default_webhook_path(self):
        assert make_adapter()._webhook_path == "/webhook/qq_bot"

    def test_access_token_empty_initially(self):
        assert make_adapter()._access_token == ""

    def test_token_expires_at_zero(self):
        assert make_adapter()._token_expires_at == 0.0

    def test_runner_none_initially(self):
        assert make_adapter()._runner is None

    def test_custom_app_id(self):
        assert make_adapter(app_id="app001")._app_id == "app001"

    def test_custom_client_secret(self):
        assert make_adapter(client_secret="sec001")._client_secret == "sec001"

    def test_port_coerced_from_string(self):
        assert make_adapter(port="9000")._port == 9000

    def test_custom_bot_openid(self):
        assert make_adapter(bot_openid="bot_open_001")._bot_openid == "bot_open_001"

    def test_channel_id_class(self):
        assert QQBotAdapter.channel_id == "qq_bot"

    def test_channel_id_instance(self):
        assert make_adapter().channel_id == "qq_bot"


# ===========================================================================
# 3. is_connected
# ===========================================================================


class TestIsConnected:
    def test_not_connected_initially(self):
        assert not make_adapter().is_connected

    def test_connected_when_runner_set(self):
        a = make_adapter()
        a._runner = MagicMock()
        assert a.is_connected

    def test_not_connected_after_runner_cleared(self):
        a = make_adapter()
        a._runner = MagicMock()
        a._runner = None
        assert not a.is_connected


# ===========================================================================
# 4. connect() / disconnect()
# ===========================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_connect_sets_runner(self):
        a = make_adapter()
        with patch("aiohttp.web.AppRunner") as mr, patch("aiohttp.web.TCPSite") as ms:
            mock_runner = AsyncMock()
            mr.return_value = mock_runner
            ms.return_value = AsyncMock()
            await a.connect()
        assert a._runner is not None

    @pytest.mark.asyncio
    async def test_connect_calls_setup(self):
        a = make_adapter()
        with patch("aiohttp.web.AppRunner") as mr, patch("aiohttp.web.TCPSite") as ms:
            mock_runner = AsyncMock()
            mr.return_value = mock_runner
            ms.return_value = AsyncMock()
            await a.connect()
        mock_runner.setup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_calls_cleanup(self):
        a = make_adapter()
        runner = AsyncMock()
        a._runner = runner
        await a.disconnect()
        runner.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_runner(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_not_connected(self):
        a = make_adapter()
        await a.disconnect()

    @pytest.mark.asyncio
    async def test_double_disconnect_safe(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        await a.disconnect()
        assert a._runner is None


# ===========================================================================
# 5. _verify_signature()
# ===========================================================================


class TestVerifySignature:
    def test_valid_signature(self):
        a = make_adapter(client_secret="sec")
        body = b'{"test": true}'
        sig = _hmac_sig("sec", "ts1", body)
        assert a._verify_signature(body, "ts1", sig) is True

    def test_invalid_signature(self):
        a = make_adapter(client_secret="sec")
        assert a._verify_signature(b"body", "ts", "badsig") is False

    def test_empty_sig_with_secret_set(self):
        a = make_adapter(client_secret="sec")
        assert a._verify_signature(b"body", "ts", "") is False

    def test_no_secret_dev_mode_accepts_all(self):
        a = make_adapter(client_secret="")
        assert a._verify_signature(b"body", "ts", "") is True

    def test_no_secret_accepts_any_sig(self):
        a = make_adapter(client_secret="")
        assert a._verify_signature(b"body", "ts", "anything") is True

    def test_tampered_body_fails(self):
        a = make_adapter(client_secret="sec")
        body = b"original"
        sig = _hmac_sig("sec", "ts", body)
        assert a._verify_signature(b"tampered", "ts", sig) is False

    def test_uses_sha256_not_sha1(self):
        a = make_adapter(client_secret="sec")
        body = b"body"
        sha1_sig = hmac.new(b"sec", b"ts" + body, hashlib.sha1).hexdigest()
        sha256_sig = _hmac_sig("sec", "ts", body)
        assert a._verify_signature(body, "ts", sha256_sig) is True
        assert a._verify_signature(body, "ts", sha1_sig) is False

    def test_timestamp_prepended_to_body(self):
        a = make_adapter(client_secret="sec")
        body = b"body"
        sig_with_ts = _hmac_sig("sec", "1234", body)
        sig_no_ts = hmac.new(b"sec", body, hashlib.sha256).hexdigest()
        assert a._verify_signature(body, "1234", sig_with_ts) is True
        assert a._verify_signature(body, "1234", sig_no_ts) is False


# ===========================================================================
# 6. _make_challenge_response()
# ===========================================================================


class TestMakeChallengeResponse:
    def test_returns_hmac_hex(self):
        a = make_adapter(client_secret="sec")
        expected = hmac.new(b"sec", b"1234abcdef", hashlib.sha256).hexdigest()
        assert a._make_challenge_response("abcdef", "1234") == expected

    def test_event_ts_before_plain_token(self):
        a = make_adapter(client_secret="sec")
        r1 = a._make_challenge_response("token", "ts")
        r2 = a._make_challenge_response("ts", "token")
        assert r1 != r2

    def test_empty_secret_returns_empty_hmac(self):
        a = make_adapter(client_secret="")
        result = a._make_challenge_response("tok", "ts")
        expected = hmac.new(b"", b"tstok", hashlib.sha256).hexdigest()
        assert result == expected


# ===========================================================================
# 7. _get_access_token()
# ===========================================================================


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_returns_cached_token(self):
        a = make_adapter()
        a._access_token = "cached"
        a._token_expires_at = time.time() + 3600
        assert await a._get_access_token() == "cached"

    @pytest.mark.asyncio
    async def test_refreshes_expired_token(self):
        a = make_adapter()
        a._token_expires_at = time.time() - 1
        resp = fake_token_response("fresh")
        with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
            assert await a._get_access_token() == "fresh"

    @pytest.mark.asyncio
    async def test_refreshes_within_60s_buffer(self):
        a = make_adapter()
        a._access_token = "expiring"
        a._token_expires_at = time.time() + 30
        resp = fake_token_response("newtoken")
        with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
            assert await a._get_access_token() == "newtoken"

    @pytest.mark.asyncio
    async def test_returns_empty_no_app_id(self):
        assert await make_adapter(app_id="")._get_access_token() == ""

    @pytest.mark.asyncio
    async def test_returns_empty_no_secret(self):
        assert await make_adapter(client_secret="")._get_access_token() == ""

    @pytest.mark.asyncio
    async def test_stores_new_token(self):
        a = make_adapter()
        resp = fake_token_response("stored")
        with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
            await a._get_access_token()
        assert a._access_token == "stored"

    @pytest.mark.asyncio
    async def test_stores_expiry(self):
        a = make_adapter()
        before = time.time()
        resp = fake_token_response("tok", "7200")
        with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
            await a._get_access_token()
        assert a._token_expires_at >= before + 7200 - 1

    @pytest.mark.asyncio
    async def test_handles_string_expires_in(self):
        a = make_adapter()
        resp = fake_token_response("tok", "3600")
        with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
            result = await a._get_access_token()
        assert result == "tok"

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            assert await a._get_access_token() == ""

    @pytest.mark.asyncio
    async def test_empty_token_in_response_returns_empty(self):
        a = make_adapter()
        resp = MagicMock()
        resp.json = MagicMock(return_value={"message": "invalid credentials"})
        with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
            assert await a._get_access_token() == ""

    @pytest.mark.asyncio
    async def test_posts_to_apptoken_url(self):
        a = make_adapter()
        resp = fake_token_response()
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        assert client.post.call_args[0][0] == _APPTOKEN_URL

    @pytest.mark.asyncio
    async def test_sends_app_id_and_secret(self):
        a = make_adapter(app_id="appA", client_secret="secB")
        resp = fake_token_response()
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        body = client.post.call_args[1]["json"]
        assert body["appId"] == "appA"
        assert body["clientSecret"] == "secB"


# ===========================================================================
# 8. _extract_message()
# ===========================================================================


class TestExtractMessage:
    def test_at_message_create_sender_id(self):
        a = make_adapter()
        ev = _msg_event("AT_MESSAGE_CREATE", author_id="alice")
        s, t, th, m = a._extract_message("AT_MESSAGE_CREATE", ev["d"])
        assert s == "alice"

    def test_at_message_create_thread_is_channel(self):
        a = make_adapter()
        ev = _msg_event("AT_MESSAGE_CREATE", channel_id="chan99")
        _, _, th, _ = a._extract_message("AT_MESSAGE_CREATE", ev["d"])
        assert th == "chan99"

    def test_at_message_strips_mentions(self):
        a = make_adapter()
        ev = _msg_event("AT_MESSAGE_CREATE", content="<@!bot123> hello bot")
        _, text, _, _ = a._extract_message("AT_MESSAGE_CREATE", ev["d"])
        assert text == "hello bot"
        assert "<@!" not in text

    def test_direct_message_create_sender_id(self):
        a = make_adapter()
        ev = _msg_event("DIRECT_MESSAGE_CREATE", author_id="bob")
        s, t, th, m = a._extract_message("DIRECT_MESSAGE_CREATE", ev["d"])
        assert s == "bob"

    def test_direct_message_create_thread_is_guild(self):
        a = make_adapter()
        ev = _msg_event("DIRECT_MESSAGE_CREATE", guild_id="guild99")
        _, _, th, _ = a._extract_message("DIRECT_MESSAGE_CREATE", ev["d"])
        assert th == "guild99"

    def test_direct_message_content_not_stripped(self):
        a = make_adapter()
        ev = _msg_event("DIRECT_MESSAGE_CREATE", content="hello directly")
        _, text, _, _ = a._extract_message("DIRECT_MESSAGE_CREATE", ev["d"])
        assert text == "hello directly"

    def test_c2c_message_sender_is_user_openid(self):
        a = make_adapter()
        ev = _msg_event("C2C_MESSAGE_CREATE", user_openid="openid_xyz")
        s, _, _, _ = a._extract_message("C2C_MESSAGE_CREATE", ev["d"])
        assert s == "openid_xyz"

    def test_c2c_thread_is_sender_id(self):
        a = make_adapter()
        ev = _msg_event("C2C_MESSAGE_CREATE", user_openid="openid_abc")
        _, _, th, _ = a._extract_message("C2C_MESSAGE_CREATE", ev["d"])
        assert th == "openid_abc"

    def test_group_at_message_sender_is_member_openid(self):
        a = make_adapter()
        ev = _msg_event("GROUP_AT_MESSAGE_CREATE", member_openid="member_xyz")
        s, _, _, _ = a._extract_message("GROUP_AT_MESSAGE_CREATE", ev["d"])
        assert s == "member_xyz"

    def test_group_at_message_thread_is_group_openid(self):
        a = make_adapter()
        ev = _msg_event("GROUP_AT_MESSAGE_CREATE", group_openid="grp_abc")
        _, _, th, _ = a._extract_message("GROUP_AT_MESSAGE_CREATE", ev["d"])
        assert th == "grp_abc"

    def test_group_at_message_strips_mentions(self):
        a = make_adapter()
        ev = _msg_event("GROUP_AT_MESSAGE_CREATE", content="<@!bot> tell me stuff")
        _, text, _, _ = a._extract_message("GROUP_AT_MESSAGE_CREATE", ev["d"])
        assert text == "tell me stuff"

    def test_msg_id_extracted(self):
        a = make_adapter()
        ev = _msg_event("AT_MESSAGE_CREATE", msg_id="msg-unique-99")
        _, _, _, m = a._extract_message("AT_MESSAGE_CREATE", ev["d"])
        assert m == "msg-unique-99"


# ===========================================================================
# 9. _parse_target()
# ===========================================================================


class TestParseTarget:
    def test_bare_string_is_channel(self):
        assert make_adapter()._parse_target("chan1") == ("channel", "chan1")

    def test_channel_prefix(self):
        assert make_adapter()._parse_target("channel:chan1") == ("channel", "chan1")

    def test_dm_prefix(self):
        assert make_adapter()._parse_target("dm:guild1") == ("dm", "guild1")

    def test_group_prefix(self):
        assert make_adapter()._parse_target("group:grp1") == ("group", "grp1")

    def test_c2c_prefix(self):
        assert make_adapter()._parse_target("c2c:user1") == ("c2c", "user1")

    def test_user_prefix_becomes_c2c(self):
        assert make_adapter()._parse_target("user:user2") == ("c2c", "user2")

    def test_colon_in_value_preserved(self):
        kind, val = make_adapter()._parse_target("channel:id:with:colons")
        assert kind == "channel"
        assert val == "id:with:colons"


# ===========================================================================
# 10. _handle_webhook()
# ===========================================================================


class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_challenge_response_correct_fields(self):
        a = make_adapter(client_secret="sec")
        payload = {"op": _OP_CHALLENGE, "d": {"plain_token": "tok123", "event_ts": "1234567890"}}
        req = _make_request(payload, "sec")
        resp = await a._handle_webhook(req)
        data = json.loads(resp.text)
        assert data["plain_token"] == "tok123"
        expected_sig = a._make_challenge_response("tok123", "1234567890")
        assert data["signature"] == expected_sig

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self):
        a = make_adapter(client_secret="sec")
        req = _make_request(_msg_event(), "wrongsec")
        resp = await a._handle_webhook(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_malformed_json_returns_400(self):
        a = make_adapter(client_secret="")
        req = MagicMock()
        req.headers = {"X-Signature-Ed25519": "", "X-Signature-Timestamp": "ts"}
        req.read = AsyncMock(return_value=b"NOT JSON {{{")
        resp = await a._handle_webhook(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_at_message_dispatched(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        payload = _msg_event("AT_MESSAGE_CREATE", content="<@!bot> hello world")
        req = _make_request(payload, "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "hello world"

    @pytest.mark.asyncio
    async def test_c2c_message_dispatched(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("C2C_MESSAGE_CREATE", content="private msg"), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].text == "private msg"

    @pytest.mark.asyncio
    async def test_group_at_message_dispatched(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("GROUP_AT_MESSAGE_CREATE", content="<@!bot> group hello"), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].text == "group hello"

    @pytest.mark.asyncio
    async def test_direct_message_create_dispatched(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("DIRECT_MESSAGE_CREATE", content="dm here"), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].text == "dm here"

    @pytest.mark.asyncio
    async def test_unknown_event_not_dispatched(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request({"op": 0, "t": "MESSAGE_DELETE", "d": {}, "s": 1}, "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_empty_content_not_dispatched(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("C2C_MESSAGE_CREATE", content=""), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_mention_only_content_not_dispatched(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("AT_MESSAGE_CREATE", content="<@!bot>"), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_echo_guard_drops_bot_openid(self):
        a = make_adapter(client_secret="mysecret", bot_openid="user_open_001")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("C2C_MESSAGE_CREATE", content="echo", user_openid="user_open_001"), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_channel_id_in_message(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("C2C_MESSAGE_CREATE", content="hello"), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].channel == "qq_bot"

    @pytest.mark.asyncio
    async def test_raw_contains_event_type(self):
        a = make_adapter(client_secret="mysecret")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request(_msg_event("C2C_MESSAGE_CREATE", content="hello", msg_id="raw-check"), "mysecret")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].raw["event_type"] == "C2C_MESSAGE_CREATE"
        assert msgs[0].raw["msg_id"] == "raw-check"

    @pytest.mark.asyncio
    async def test_no_secret_dev_mode_accepts_all(self):
        a = make_adapter(client_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = MagicMock()
        req.headers = {"X-Signature-Ed25519": "", "X-Signature-Timestamp": "ts"}
        body = json.dumps(_msg_event("C2C_MESSAGE_CREATE", content="devmode")).encode()
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].text == "devmode"


# ===========================================================================
# 11. _handle_health()
# ===========================================================================


class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        a = make_adapter()
        req = MagicMock()
        resp = await a._handle_health(req)
        assert resp.status == 200


# ===========================================================================
# 12. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        assert await make_adapter().send("", "hi") is None

    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="")):
            assert await a.send("channel:chan1", "hi") is None

    @pytest.mark.asyncio
    async def test_success_returns_target(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
                assert await a.send("channel:chan1", "Hello!") == "channel:chan1"

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(401)
            with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
                assert await a.send("channel:chan1", "hi") is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            client = AsyncMock()
            client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
            client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=client):
                assert await a.send("channel:chan1", "hi") is None

    @pytest.mark.asyncio
    async def test_channel_target_uses_guild_api(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("channel:chan99", "hi")
        url = client.post.call_args[0][0]
        assert _GUILD_API in url
        assert "chan99" in url

    @pytest.mark.asyncio
    async def test_dm_target_uses_guild_dms_api(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("dm:guild99", "hi")
        url = client.post.call_args[0][0]
        assert "/dms/guild99/messages" in url

    @pytest.mark.asyncio
    async def test_group_target_uses_group_api(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("group:grp99", "hi")
        url = client.post.call_args[0][0]
        assert _GROUP_API in url
        assert "grp99" in url

    @pytest.mark.asyncio
    async def test_c2c_target_uses_group_users_api(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("c2c:user99", "hi")
        url = client.post.call_args[0][0]
        assert "/users/user99/messages" in url

    @pytest.mark.asyncio
    async def test_user_prefix_uses_c2c_endpoint(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("user:open99", "hi")
        url = client.post.call_args[0][0]
        assert "/users/open99/messages" in url

    @pytest.mark.asyncio
    async def test_bare_target_uses_channel_endpoint(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("bareChannel", "hi")
        url = client.post.call_args[0][0]
        assert "/channels/bareChannel/messages" in url

    @pytest.mark.asyncio
    async def test_qqbot_auth_header(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="mytoken")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("channel:chan1", "hi")
        headers = client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "QQBot mytoken"

    @pytest.mark.asyncio
    async def test_201_status_also_success(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(201)
            with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
                assert await a.send("channel:chan1", "hi") == "channel:chan1"

    @pytest.mark.asyncio
    async def test_unicode_message(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(200)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("channel:chan1", "你好 🌸")
        assert result == "channel:chan1"


# ===========================================================================
# 13. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_no_app_id_returns_false(self):
        assert await make_adapter(app_id="").ping() is False

    @pytest.mark.asyncio
    async def test_no_secret_returns_false(self):
        assert await make_adapter(client_secret="").ping() is False

    @pytest.mark.asyncio
    async def test_token_error_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="")):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_200_returns_true(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(return_value={"id": "bot123"})
            client = fake_http_client(get=resp)
            with patch("httpx.AsyncClient", return_value=client):
                assert await a.ping() is True

    @pytest.mark.asyncio
    async def test_401_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = MagicMock()
            resp.status_code = 401
            with patch("httpx.AsyncClient", return_value=fake_http_client(get=resp)):
                assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            client = AsyncMock()
            client.__aenter__ = AsyncMock(side_effect=ConnectionError())
            client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=client):
                assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_calls_users_at_me(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = MagicMock()
            resp.status_code = 200
            client = fake_http_client(get=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.ping()
        url = client.get.call_args[0][0]
        assert "/users/@me" in url


# ===========================================================================
# 14. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_app_id(self):
        assert "app_id" in make_adapter().get_config_schema()["required"]

    def test_required_has_client_secret(self):
        assert "client_secret" in make_adapter().get_config_schema()["required"]

    def test_properties_present(self):
        props = make_adapter().get_config_schema()["properties"]
        for k in ("app_id", "client_secret", "bot_openid", "host", "port", "webhook_path"):
            assert k in props

    def test_port_default(self):
        assert make_adapter().get_config_schema()["properties"]["port"]["default"] == 8093

    def test_host_default(self):
        assert make_adapter().get_config_schema()["properties"]["host"]["default"] == "0.0.0.0"

    def test_webhook_path_default(self):
        assert make_adapter().get_config_schema()["properties"]["webhook_path"]["default"] == "/webhook/qq_bot"


# ===========================================================================
# 15. Constants
# ===========================================================================


class TestConstants:
    def test_apptoken_url(self):
        assert _APPTOKEN_URL == "https://bots.qq.com/app/getAppAccessToken"

    def test_guild_api(self):
        assert _GUILD_API == "https://api.sgroup.qq.com"

    def test_group_api(self):
        assert _GROUP_API == "https://api.q.qq.com"

    def test_op_challenge(self):
        assert _OP_CHALLENGE == 13


# ===========================================================================
# 16. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "qq_bot" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_multiple_events_dispatched_in_order(self):
        a = make_adapter(client_secret="sec")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        for i in range(3):
            req = _make_request(_msg_event("C2C_MESSAGE_CREATE", content=f"msg{i}", msg_id=str(i)), "sec")
            await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(msgs) == 3
        assert {m.text for m in msgs} == {"msg0", "msg1", "msg2"}

    @pytest.mark.asyncio
    async def test_challenge_not_dispatched_as_message(self):
        a = make_adapter(client_secret="sec")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _make_request({"op": _OP_CHALLENGE, "d": {"plain_token": "t", "event_ts": "ts"}}, "sec")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_sender_name_falls_back_to_sender_id(self):
        a = make_adapter(client_secret="sec")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        ev = _msg_event("C2C_MESSAGE_CREATE", content="hi", user_openid="openid123")
        ev["d"]["author"] = {"user_openid": "openid123"}
        req = _make_request(ev, "sec")
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "openid123"
