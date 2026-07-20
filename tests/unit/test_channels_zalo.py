"""Unit tests for neuralcleave.channels.zalo — ZaloAdapter.

Covers:
  - Constructor / defaults / config parsing
  - is_connected lifecycle (runner-based)
  - connect() / disconnect()
  - _verify_signature() — valid, invalid, no secret dev mode
  - _get_access_token() — cache hit, refresh success, refresh failure, missing creds
  - _handle_webhook() — signature check, all event types, echo guard, empty text, dispatch
  - _handle_health() — GET returns 200
  - send() — success, no target, no token, API error, network error
  - ping() — token valid 200, 401, no creds, network error
  - get_config_schema() — shape and required fields
  - Constants
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

from neuralcleave.channels.zalo import (
    _OA_INFO_URL,
    _SEND_URL,
    _TOKEN_URL,
    ZaloAdapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides: Any) -> ZaloAdapter:
    cfg: dict[str, Any] = {
        "app_id": "123456789",
        "app_secret": "mysecret",
        "refresh_token": "myrefreshtoken",
        **overrides,
    }
    return ZaloAdapter(cfg)


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_event(
    event_name: str = "user_send_text",
    sender_id: str = "user123",
    user_id_by_app: str = "app_user456",
    oa_id: str = "oa789",
    text: str = "Hello!",
    ts: int = 1700000000,
    msg_id: str = "msg-001",
) -> dict[str, Any]:
    return {
        "app_id": "123456789",
        "user_id_by_app": user_id_by_app,
        "event_name": event_name,
        "timestamp": ts,
        "sender": {"id": sender_id, "display_name": "TestUser"},
        "recipient": {"id": oa_id},
        "message": {"msg_id": msg_id, "text": text},
    }


async def _post_event(adapter: ZaloAdapter, event: dict, secret: str = "mysecret") -> Any:
    from aiohttp.test_utils import make_mocked_request
    body = json.dumps(event).encode()
    sig = _sign(secret, body)
    req = make_mocked_request(
        "POST",
        adapter._webhook_path,
        headers={"X-ZAlo-Signature": sig, "Content-Type": "application/json"},
    )
    req._payload = MagicMock()
    req._payload.read = AsyncMock(return_value=body)
    req.read = AsyncMock(return_value=body)
    return await adapter._handle_webhook(req)


def fake_token_response(token: str = "newtoken", expires: int = 3600) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(
        return_value={"access_token": token, "expires_in": expires, "error": 0}
    )
    return resp


def fake_send_response(error: int = 0, msg_id: str = "sent-001") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"error": error, "message": {"msg_id": msg_id}})
    return resp


def fake_http_client(**method_responses: MagicMock) -> MagicMock:
    client = AsyncMock()
    for method, resp in method_responses.items():
        setattr(client, method, AsyncMock(return_value=resp))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def fake_info_response(status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value={"error": 0, "data": {"oa_id": "oa789"}})
    return resp


# ===========================================================================
# 1. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_app_id_empty(self):
        assert ZaloAdapter({})._app_id == ""

    def test_default_app_secret_empty(self):
        assert ZaloAdapter({})._app_secret == ""

    def test_default_refresh_token_empty(self):
        assert ZaloAdapter({})._refresh_token == ""

    def test_default_bot_oa_id_empty(self):
        assert ZaloAdapter({})._bot_oa_id == ""

    def test_default_host(self):
        assert make_adapter()._host == "0.0.0.0"

    def test_default_port(self):
        assert make_adapter()._port == 8091

    def test_default_webhook_path(self):
        assert make_adapter()._webhook_path == "/webhook/zalo"

    def test_access_token_empty_initially(self):
        assert make_adapter()._access_token == ""

    def test_token_expires_at_zero_initially(self):
        assert make_adapter()._token_expires_at == 0.0

    def test_runner_none_initially(self):
        assert make_adapter()._runner is None

    def test_custom_app_id(self):
        assert make_adapter(app_id="abc123")._app_id == "abc123"

    def test_custom_port_string_coerced(self):
        assert make_adapter(port="9000")._port == 9000

    def test_custom_host(self):
        assert make_adapter(host="127.0.0.1")._host == "127.0.0.1"

    def test_custom_webhook_path(self):
        assert make_adapter(webhook_path="/zalo/in")._webhook_path == "/zalo/in"

    def test_custom_bot_oa_id(self):
        assert make_adapter(bot_oa_id="oa999")._bot_oa_id == "oa999"

    def test_channel_id(self):
        assert ZaloAdapter.channel_id == "zalo"

    def test_channel_id_on_instance(self):
        assert make_adapter().channel_id == "zalo"


# ===========================================================================
# 2. is_connected
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
# 3. connect() / disconnect()
# ===========================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_connect_sets_runner(self):
        a = make_adapter()
        with patch("aiohttp.web.AppRunner") as mock_runner_cls, \
             patch("aiohttp.web.TCPSite") as mock_site_cls:
            mock_runner = AsyncMock()
            mock_runner_cls.return_value = mock_runner
            mock_site = AsyncMock()
            mock_site_cls.return_value = mock_site
            await a.connect()
        assert a._runner is not None

    @pytest.mark.asyncio
    async def test_connect_calls_runner_setup(self):
        a = make_adapter()
        with patch("aiohttp.web.AppRunner") as mock_runner_cls, \
             patch("aiohttp.web.TCPSite") as mock_site_cls:
            mock_runner = AsyncMock()
            mock_runner_cls.return_value = mock_runner
            mock_site = AsyncMock()
            mock_site_cls.return_value = mock_site
            await a.connect()
        mock_runner.setup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_starts_site(self):
        a = make_adapter()
        with patch("aiohttp.web.AppRunner") as mock_runner_cls, \
             patch("aiohttp.web.TCPSite") as mock_site_cls:
            mock_runner = AsyncMock()
            mock_runner_cls.return_value = mock_runner
            mock_site = AsyncMock()
            mock_site_cls.return_value = mock_site
            await a.connect()
        mock_site.start.assert_awaited_once()

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
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_double_disconnect_safe(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        await a.disconnect()
        assert a._runner is None


# ===========================================================================
# 4. _verify_signature()
# ===========================================================================


class TestVerifySignature:
    def test_valid_signature(self):
        a = make_adapter(app_secret="secret123")
        body = b'{"event": "test"}'
        sig = _sign("secret123", body)
        assert a._verify_signature(body, sig) is True

    def test_invalid_signature(self):
        a = make_adapter(app_secret="secret123")
        body = b'{"event": "test"}'
        assert a._verify_signature(body, "badhash") is False

    def test_tampered_body(self):
        a = make_adapter(app_secret="secret123")
        body = b'{"event": "test"}'
        sig = _sign("secret123", body)
        tampered = b'{"event": "tampered"}'
        assert a._verify_signature(tampered, sig) is False

    def test_empty_sig_with_secret_set_returns_false(self):
        a = make_adapter(app_secret="secret123")
        assert a._verify_signature(b"body", "") is False

    def test_no_secret_dev_mode_accepts_all(self):
        a = make_adapter(app_secret="")
        assert a._verify_signature(b"body", "") is True

    def test_no_secret_dev_mode_ignores_sig(self):
        a = make_adapter(app_secret="")
        assert a._verify_signature(b"body", "anysig") is True

    def test_different_secrets_fail(self):
        a = make_adapter(app_secret="correct")
        body = b"body"
        sig = _sign("wrong", body)
        assert a._verify_signature(body, sig) is False

    def test_empty_body_valid_sig(self):
        a = make_adapter(app_secret="secret")
        sig = _sign("secret", b"")
        assert a._verify_signature(b"", sig) is True


# ===========================================================================
# 5. _get_access_token()
# ===========================================================================


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_returns_cached_token_when_valid(self):
        a = make_adapter()
        a._access_token = "cachedtoken"
        a._token_expires_at = time.time() + 3600
        result = await a._get_access_token()
        assert result == "cachedtoken"

    @pytest.mark.asyncio
    async def test_refreshes_when_expired(self):
        a = make_adapter()
        a._access_token = "oldtoken"
        a._token_expires_at = time.time() - 1
        resp = fake_token_response("freshtoken")
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a._get_access_token()
        assert result == "freshtoken"

    @pytest.mark.asyncio
    async def test_refreshes_within_60s_buffer(self):
        a = make_adapter()
        a._access_token = "oldtoken"
        a._token_expires_at = time.time() + 30
        resp = fake_token_response("freshtoken")
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a._get_access_token()
        assert result == "freshtoken"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_refresh_token(self):
        a = make_adapter(refresh_token="")
        result = await a._get_access_token()
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_app_id(self):
        a = make_adapter(app_id="")
        result = await a._get_access_token()
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_app_secret(self):
        a = make_adapter(app_secret="")
        result = await a._get_access_token()
        assert result == ""

    @pytest.mark.asyncio
    async def test_stores_new_token(self):
        a = make_adapter()
        a._token_expires_at = 0
        resp = fake_token_response("freshtoken", 3600)
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        assert a._access_token == "freshtoken"

    @pytest.mark.asyncio
    async def test_stores_expiry(self):
        a = make_adapter()
        a._token_expires_at = 0
        before = time.time()
        resp = fake_token_response("tok", 1800)
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        assert a._token_expires_at >= before + 1800 - 1

    @pytest.mark.asyncio
    async def test_updates_refresh_token_if_returned(self):
        a = make_adapter()
        a._token_expires_at = 0
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value={"access_token": "tok", "expires_in": 3600, "refresh_token": "newrefresh"})
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        assert a._refresh_token == "newrefresh"

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self):
        a = make_adapter()
        a._token_expires_at = 0
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a._get_access_token()
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_access_token_in_response_returns_empty(self):
        a = make_adapter()
        a._token_expires_at = 0
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value={"error": 40, "message": "invalid refresh token"})
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a._get_access_token()
        assert result == ""

    @pytest.mark.asyncio
    async def test_posts_to_token_url(self):
        a = make_adapter()
        a._token_expires_at = 0
        resp = fake_token_response()
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        url = client.post.call_args[0][0]
        assert url == _TOKEN_URL

    @pytest.mark.asyncio
    async def test_sends_secret_key_header(self):
        a = make_adapter(app_secret="mysecret")
        a._token_expires_at = 0
        resp = fake_token_response()
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        headers = client.post.call_args[1]["headers"]
        assert headers["secret_key"] == "mysecret"


# ===========================================================================
# 6. _handle_webhook()
# ===========================================================================


class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_valid_text_event_dispatches_message(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = _make_event(text="Hello Zalo")
        await _post_event(a, event)
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello Zalo"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self):
        a = make_adapter(app_secret="secret")
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(_make_event()).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": "badsig"})
        req.read = AsyncMock(return_value=body)
        resp = await a._handle_webhook(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_missing_signature_with_secret_set_returns_401(self):
        a = make_adapter(app_secret="secret")
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(_make_event()).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={})
        req.read = AsyncMock(return_value=body)
        resp = await a._handle_webhook(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_no_secret_dev_mode_accepts_no_sig(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        from aiohttp.test_utils import make_mocked_request
        event = _make_event()
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_unknown_event_returns_200_no_dispatch(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        from aiohttp.test_utils import make_mocked_request
        event = _make_event(event_name="user_seen_message")
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        resp = await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert resp.status == 200
        assert msgs == []

    @pytest.mark.asyncio
    async def test_image_event_dispatches_with_type_text(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        from aiohttp.test_utils import make_mocked_request
        event = _make_event(event_name="user_send_image", text="")
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert "[user_send_image]" in msgs[0].text

    @pytest.mark.asyncio
    async def test_echo_guard_bot_oa_id(self):
        a = make_adapter(bot_oa_id="app_user456", app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        from aiohttp.test_utils import make_mocked_request
        event = _make_event(user_id_by_app="app_user456")
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_empty_text_event_not_dispatched(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        from aiohttp.test_utils import make_mocked_request
        event = _make_event(event_name="user_send_text", text="")
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_sender_id_from_user_id_by_app(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = _make_event(user_id_by_app="app_uid_999")
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "app_uid_999"

    @pytest.mark.asyncio
    async def test_thread_id_is_oa_id(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = _make_event(oa_id="my_oa_id_789")
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "my_oa_id_789"

    @pytest.mark.asyncio
    async def test_timestamp_parsed_from_event(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = _make_event(ts=1700000000)
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].timestamp == 1700000000.0

    @pytest.mark.asyncio
    async def test_channel_id_in_message(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = _make_event()
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].channel == "zalo"

    @pytest.mark.asyncio
    async def test_raw_contains_event(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = _make_event(msg_id="raw-check-msg")
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].raw["message"]["msg_id"] == "raw-check-msg"

    @pytest.mark.asyncio
    async def test_malformed_json_returns_400(self):
        a = make_adapter(app_secret="")
        from aiohttp.test_utils import make_mocked_request
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=b"NOT JSON {{")
        resp = await a._handle_webhook(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_returns_200_on_success(self):
        a = make_adapter(app_secret="")
        from aiohttp.test_utils import make_mocked_request
        event = _make_event()
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_all_media_event_types_dispatched(self):
        for event_name in ("user_send_image", "user_send_sticker", "user_send_file",
                           "user_send_audio", "user_send_video"):
            a = make_adapter(app_secret="")
            msgs: list = []
            a.on_message(lambda m: msgs.append(m))
            from aiohttp.test_utils import make_mocked_request
            event = _make_event(event_name=event_name, text="")
            body = json.dumps(event).encode()
            req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
            req.read = AsyncMock(return_value=body)
            await a._handle_webhook(req)
            await asyncio.sleep(0)
            assert len(msgs) == 1, f"Expected 1 msg for {event_name}, got {len(msgs)}"


# ===========================================================================
# 7. _handle_health()
# ===========================================================================


class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from aiohttp.test_utils import make_mocked_request
        a = make_adapter()
        req = make_mocked_request("GET", "/webhook/zalo", headers={})
        resp = await a._handle_health(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_returns_ok_text(self):
        from aiohttp.test_utils import make_mocked_request
        a = make_adapter()
        req = make_mocked_request("GET", "/webhook/zalo", headers={})
        resp = await a._handle_health(req)
        assert "OK" in resp.text.upper() or "zalo" in resp.text.lower()


# ===========================================================================
# 8. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        a = make_adapter()
        assert await a.send("", "hi") is None

    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="")):
            assert await a.send("user123", "hi") is None

    @pytest.mark.asyncio
    async def test_success_returns_target(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(error=0)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("user123", "Hello!")
        assert result == "user123"

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(error=-201)
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("user123", "Hello!")
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            client = AsyncMock()
            client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
            client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("user123", "Hello!")
        assert result is None

    @pytest.mark.asyncio
    async def test_posts_to_send_url(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("user123", "Hello!")
        url = client.post.call_args[0][0]
        assert url == _SEND_URL

    @pytest.mark.asyncio
    async def test_sends_access_token_header(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="mytoken")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("user123", "Hi")
        headers = client.post.call_args[1]["headers"]
        assert headers["access_token"] == "mytoken"

    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("user123", "Hello Zalo!")
        payload = client.post.call_args[1]["json"]
        assert payload["recipient"]["user_id"] == "user123"
        assert payload["message"]["text"] == "Hello Zalo!"

    @pytest.mark.asyncio
    async def test_unicode_text_sent(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("user123", "Xin chào 🌸")
        assert result == "user123"


# ===========================================================================
# 9. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_false(self):
        a = make_adapter(app_secret="", refresh_token="", app_id="")
        assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_200_returns_true(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_info_response(200)
            client = fake_http_client(get=resp)
            with patch("httpx.AsyncClient", return_value=client):
                assert await a.ping() is True

    @pytest.mark.asyncio
    async def test_401_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_info_response(401)
            client = fake_http_client(get=resp)
            with patch("httpx.AsyncClient", return_value=client):
                assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_no_token_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="")):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            client = AsyncMock()
            client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
            client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=client):
                assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_calls_oa_info_url(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_info_response(200)
            client = fake_http_client(get=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.ping()
        url = client.get.call_args[0][0]
        assert url == _OA_INFO_URL

    @pytest.mark.asyncio
    async def test_sends_access_token_header(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="testtoken")):
            resp = fake_info_response(200)
            client = fake_http_client(get=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.ping()
        headers = client.get.call_args[1]["headers"]
        assert headers["access_token"] == "testtoken"


# ===========================================================================
# 10. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_app_id(self):
        assert "app_id" in make_adapter().get_config_schema()["required"]

    def test_required_has_app_secret(self):
        assert "app_secret" in make_adapter().get_config_schema()["required"]

    def test_required_has_refresh_token(self):
        assert "refresh_token" in make_adapter().get_config_schema()["required"]

    def test_properties_has_all_keys(self):
        props = make_adapter().get_config_schema()["properties"]
        for key in ("app_id", "app_secret", "refresh_token", "bot_oa_id",
                    "host", "port", "webhook_path"):
            assert key in props, f"Missing: {key}"

    def test_port_default(self):
        assert make_adapter().get_config_schema()["properties"]["port"]["default"] == 8091

    def test_host_default(self):
        assert make_adapter().get_config_schema()["properties"]["host"]["default"] == "0.0.0.0"

    def test_webhook_path_default(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["webhook_path"]["default"] == "/webhook/zalo"


# ===========================================================================
# 11. Constants
# ===========================================================================


class TestConstants:
    def test_token_url(self):
        assert _TOKEN_URL == "https://oauth.zaloapp.com/v4/oa/access_token"

    def test_send_url(self):
        assert _SEND_URL == "https://openapi.zalo.me/v3.0/oa/message/cs"

    def test_oa_info_url(self):
        assert _OA_INFO_URL == "https://openapi.zalo.me/v2.0/oa/info"


# ===========================================================================
# 12. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "zalo" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_send_uses_fresh_token_when_cached_expires_soon(self):
        a = make_adapter()
        a._access_token = "expiring"
        a._token_expires_at = time.time() + 30
        refresh_resp = fake_token_response("newtoken")
        refresh_client = fake_http_client(post=refresh_resp)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = refresh_client
            send_resp = fake_send_response(0)
            refresh_client.post = AsyncMock(side_effect=[
                refresh_resp,
                send_resp,
            ])
            await a.send("user1", "hi")
        assert a._access_token == "newtoken"

    @pytest.mark.asyncio
    async def test_concurrent_send_uses_cached_token(self):
        a = make_adapter()
        a._access_token = "validtoken"
        a._token_expires_at = time.time() + 3600
        resp = fake_send_response(0)
        client = fake_http_client(post=resp)
        with patch("httpx.AsyncClient", return_value=client):
            results = await asyncio.gather(
                a.send("user1", "msg1"),
                a.send("user2", "msg2"),
            )
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_display_name_falls_back_to_sender_id(self):
        a = make_adapter(app_secret="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = _make_event()
        event["sender"].pop("display_name", None)
        event["sender"]["id"] = "fallback_id"
        event["user_id_by_app"] = "fallback_id"
        from aiohttp.test_utils import make_mocked_request
        body = json.dumps(event).encode()
        req = make_mocked_request("POST", "/webhook/zalo", headers={"X-ZAlo-Signature": ""})
        req.read = AsyncMock(return_value=body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert msgs[0].sender_name == "fallback_id"

    @pytest.mark.asyncio
    async def test_signature_uses_sha256(self):
        a = make_adapter(app_secret="testsecret")
        body = b"test body content"
        sig_sha256 = hmac.new(b"testsecret", body, hashlib.sha256).hexdigest()
        sig_sha1 = hmac.new(b"testsecret", body, hashlib.sha1).hexdigest()
        assert a._verify_signature(body, sig_sha256) is True
        assert a._verify_signature(body, sig_sha1) is False
