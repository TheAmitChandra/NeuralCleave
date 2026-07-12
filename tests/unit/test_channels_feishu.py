"""Unit tests for cortexflow_ai.channels.feishu — FeishuAdapter.

Covers:
  - Construction / config parsing / defaults
  - is_connected lifecycle
  - connect() / disconnect()
  - _verify_request() — token matching for v1 and v2 schemas
  - _handle_webhook() — URL verification challenge, v1 events, v2 events,
    bad token, bad JSON, non-message events, echo guard
  - _handle_health()
  - _process_event_v2() — text, non-text, echo guard, sender/thread IDs,
    timestamp conversion, missing fields, raw preserved
  - _process_event_v1() — text, echo guard, thread_id, missing fields
  - _get_access_token() — success, cache hit, cache miss, errors,
    missing credentials, non-zero code
  - send() — success, empty target, no token, HTTP errors, payload structure,
    auth header, receive_id_type param, non-zero API code
  - ping() — success, no credentials, HTTP error, API code, network error
  - get_config_schema() — shape, required fields, defaults
  - Constants
  - Edge / integration cases
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.channels.feishu import (
    _BOT_INFO_URL,
    _FEISHU_API,
    _SEND_URL,
    _TOKEN_URL,
    FeishuAdapter,
)

# ===========================================================================
# Helpers / factories
# ===========================================================================


def make_adapter(**overrides: Any) -> FeishuAdapter:
    cfg: dict[str, Any] = {
        "app_id": "cli_test123",
        "app_secret": "test-secret",
        "verification_token": "vtoken-abc",
        **overrides,
    }
    return FeishuAdapter(cfg)


def make_v2_body(
    text: str = "Hello!",
    open_id: str = "ou_abc123",
    chat_id: str = "oc_chat001",
    message_type: str = "text",
    token: str = "vtoken-abc",
    create_time: str = "1700000000000",
) -> dict[str, Any]:
    content = json.dumps({"text": text}) if message_type == "text" else "{}"
    return {
        "schema": "2.0",
        "header": {
            "event_id": "ev-001",
            "event_type": "im.message.receive_v1",
            "create_time": create_time,
            "token": token,
            "app_id": "cli_test123",
            "tenant_key": "tenant-001",
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": open_id,
                    "union_id": "on_union001",
                    "user_id": "user001",
                },
                "sender_type": "user",
                "tenant_key": "tenant-001",
            },
            "message": {
                "message_id": "om_msg001",
                "chat_id": chat_id,
                "chat_type": "p2p",
                "message_type": message_type,
                "content": content,
                "create_time": create_time,
            },
        },
    }


def make_v1_body(
    text: str = "Hello!",
    open_id: str = "ou_abc123",
    chat_id: str = "oc_chat001",
    token: str = "vtoken-abc",
) -> dict[str, Any]:
    return {
        "ts": "1700000000.000",
        "uuid": "uuid-001",
        "token": token,
        "type": "event_callback",
        "event": {
            "type": "message",
            "text": text,
            "open_id": open_id,
            "user_id": "user001",
            "open_message_id": "om_msg001",
            "chat_type": "group",
            "open_chat_id": chat_id,
        },
    }


def make_url_verification_body(
    challenge: str = "ch-xyz",
    token: str = "vtoken-abc",
) -> dict[str, Any]:
    return {"challenge": challenge, "token": token, "type": "url_verification"}


def fake_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data or {})
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def fake_client(response: MagicMock) -> MagicMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def fake_aiohttp_request(json_body: dict) -> MagicMock:
    req = MagicMock()
    req.json = AsyncMock(return_value=json_body)
    return req


def fake_aiohttp_bad_json_request() -> MagicMock:
    req = MagicMock()
    req.json = AsyncMock(side_effect=ValueError("bad json"))
    return req


# ===========================================================================
# 1. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_app_id_empty(self):
        assert FeishuAdapter({})._app_id == ""

    def test_default_app_secret_empty(self):
        assert FeishuAdapter({})._app_secret == ""

    def test_default_verification_token_empty(self):
        assert FeishuAdapter({})._verification_token == ""

    def test_default_host(self):
        assert make_adapter()._host == "0.0.0.0"

    def test_default_port(self):
        assert make_adapter()._port == 8087

    def test_default_webhook_path(self):
        assert make_adapter()._webhook_path == "/webhook/feishu"

    def test_default_bot_open_id_empty(self):
        assert make_adapter()._bot_open_id == ""

    def test_default_receive_id_type(self):
        assert make_adapter()._receive_id_type == "open_id"

    def test_default_runner_none(self):
        assert make_adapter()._runner is None

    def test_default_cached_token_none(self):
        assert make_adapter()._cached_token is None

    def test_custom_app_id(self):
        assert make_adapter(app_id="cli_xyz")._app_id == "cli_xyz"

    def test_custom_app_secret(self):
        assert make_adapter(app_secret="sec-xyz")._app_secret == "sec-xyz"

    def test_custom_verification_token(self):
        assert make_adapter(verification_token="vtok-123")._verification_token == "vtok-123"

    def test_custom_host(self):
        assert make_adapter(host="127.0.0.1")._host == "127.0.0.1"

    def test_custom_port_int(self):
        assert make_adapter(port=9000)._port == 9000

    def test_custom_port_string_coerced(self):
        assert make_adapter(port="9001")._port == 9001

    def test_custom_webhook_path(self):
        assert make_adapter(webhook_path="/feishu/hook")._webhook_path == "/feishu/hook"

    def test_custom_bot_open_id(self):
        assert make_adapter(bot_open_id="ou_bot999")._bot_open_id == "ou_bot999"

    def test_receive_id_type_chat_id(self):
        assert make_adapter(receive_id_type="chat_id")._receive_id_type == "chat_id"

    def test_receive_id_type_user_id(self):
        assert make_adapter(receive_id_type="user_id")._receive_id_type == "user_id"

    def test_receive_id_type_union_id(self):
        assert make_adapter(receive_id_type="union_id")._receive_id_type == "union_id"

    def test_invalid_receive_id_type_defaults_to_open_id(self):
        assert make_adapter(receive_id_type="invalid_type")._receive_id_type == "open_id"

    def test_channel_id(self):
        assert FeishuAdapter.channel_id == "feishu"

    def test_empty_config(self):
        a = FeishuAdapter({})
        assert a._app_id == ""
        assert a._port == 8087


# ===========================================================================
# 2. is_connected
# ===========================================================================


class TestIsConnected:
    def test_not_connected_initially(self):
        assert not make_adapter().is_connected

    def test_connected_after_runner_set(self):
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
        mock_runner = AsyncMock()
        mock_site = AsyncMock()
        with (
            patch("aiohttp.web.Application"),
            patch("aiohttp.web.AppRunner", return_value=mock_runner),
            patch("aiohttp.web.TCPSite", return_value=mock_site),
        ):
            await a.connect()
        assert a._runner is mock_runner

    @pytest.mark.asyncio
    async def test_connect_calls_setup(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        mock_site = AsyncMock()
        with (
            patch("aiohttp.web.Application"),
            patch("aiohttp.web.AppRunner", return_value=mock_runner),
            patch("aiohttp.web.TCPSite", return_value=mock_site),
        ):
            await a.connect()
        mock_runner.setup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_starts_site(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        mock_site = AsyncMock()
        with (
            patch("aiohttp.web.Application"),
            patch("aiohttp.web.AppRunner", return_value=mock_runner),
            patch("aiohttp.web.TCPSite", return_value=mock_site),
        ):
            await a.connect()
        mock_site.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_runner(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_disconnect_calls_cleanup(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        a._runner = mock_runner
        await a.disconnect()
        mock_runner.cleanup.assert_awaited_once()

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

    @pytest.mark.asyncio
    async def test_is_connected_false_after_disconnect(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        assert not a.is_connected


# ===========================================================================
# 4. _verify_request()
# ===========================================================================


class TestVerifyRequest:
    def test_no_token_configured_accepts_all(self):
        a = make_adapter(verification_token="")
        assert a._verify_request({"token": "anything"}) is True

    def test_no_token_configured_accepts_empty_body(self):
        a = make_adapter(verification_token="")
        assert a._verify_request({}) is True

    def test_v1_correct_token_returns_true(self):
        a = make_adapter()
        assert a._verify_request({"token": "vtoken-abc"}) is True

    def test_v1_wrong_token_returns_false(self):
        a = make_adapter()
        assert a._verify_request({"token": "wrong-token"}) is False

    def test_v1_empty_token_returns_false(self):
        a = make_adapter()
        assert a._verify_request({"token": ""}) is False

    def test_v2_correct_token_in_header_returns_true(self):
        a = make_adapter()
        assert a._verify_request({"schema": "2.0", "header": {"token": "vtoken-abc"}}) is True

    def test_v2_wrong_token_in_header_returns_false(self):
        a = make_adapter()
        assert a._verify_request({"schema": "2.0", "header": {"token": "wrong"}}) is False

    def test_no_token_field_and_no_header_returns_false(self):
        a = make_adapter()
        assert a._verify_request({"type": "event_callback"}) is False

    def test_v2_empty_header_returns_false(self):
        a = make_adapter()
        assert a._verify_request({"schema": "2.0", "header": {}}) is False

    def test_v1_token_takes_priority_over_header(self):
        a = make_adapter()
        body = {"token": "vtoken-abc", "header": {"token": "wrong"}}
        assert a._verify_request(body) is True

    def test_token_case_sensitive(self):
        a = make_adapter(verification_token="MyToken")
        assert a._verify_request({"token": "mytoken"}) is False

    def test_exact_match_required(self):
        a = make_adapter(verification_token="abc")
        assert a._verify_request({"token": "abcd"}) is False


# ===========================================================================
# 5. _handle_health()
# ===========================================================================


class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        a = make_adapter()
        resp = await a._handle_health(MagicMock())
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_health_body_contains_feishu(self):
        a = make_adapter()
        resp = await a._handle_health(MagicMock())
        assert b"Feishu" in resp.body or b"OK" in resp.body


# ===========================================================================
# 6. _handle_webhook() — URL verification
# ===========================================================================


class TestHandleWebhookUrlVerification:
    @pytest.mark.asyncio
    async def test_url_verification_returns_challenge(self):
        a = make_adapter()
        req = fake_aiohttp_request(make_url_verification_body())
        resp = await a._handle_webhook(req)
        assert resp.status == 200
        data = json.loads(resp.body)
        assert data["challenge"] == "ch-xyz"

    @pytest.mark.asyncio
    async def test_url_verification_wrong_token_returns_401(self):
        a = make_adapter()
        body = make_url_verification_body(token="wrong-token")
        req = fake_aiohttp_request(body)
        resp = await a._handle_webhook(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_url_verification_no_token_config_accepts(self):
        a = make_adapter(verification_token="")
        body = make_url_verification_body(token="")
        req = fake_aiohttp_request(body)
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_url_verification_empty_challenge_returned(self):
        a = make_adapter()
        body = {"type": "url_verification", "token": "vtoken-abc"}
        req = fake_aiohttp_request(body)
        resp = await a._handle_webhook(req)
        assert resp.status == 200
        data = json.loads(resp.body)
        assert data["challenge"] == ""

    @pytest.mark.asyncio
    async def test_url_verification_custom_challenge(self):
        a = make_adapter()
        body = make_url_verification_body(challenge="test-challenge-999")
        req = fake_aiohttp_request(body)
        resp = await a._handle_webhook(req)
        data = json.loads(resp.body)
        assert data["challenge"] == "test-challenge-999"


# ===========================================================================
# 7. _handle_webhook() — event routing
# ===========================================================================


class TestHandleWebhookEvents:
    @pytest.mark.asyncio
    async def test_bad_json_returns_400(self):
        a = make_adapter()
        req = fake_aiohttp_bad_json_request()
        resp = await a._handle_webhook(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self):
        a = make_adapter()
        body = make_v1_body(token="wrong-token")
        req = fake_aiohttp_request(body)
        resp = await a._handle_webhook(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_no_token_configured_accepts_any(self):
        a = make_adapter(verification_token="")
        body = make_v1_body(token="anything")
        req = fake_aiohttp_request(body)
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_v1_message_event_dispatched(self):
        a = make_adapter()
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        req = fake_aiohttp_request(make_v1_body(text="hi"))
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(dispatched) == 1
        assert dispatched[0].text == "hi"

    @pytest.mark.asyncio
    async def test_v2_message_event_dispatched(self):
        a = make_adapter()
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        req = fake_aiohttp_request(make_v2_body(text="hello v2"))
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(dispatched) == 1
        assert dispatched[0].text == "hello v2"

    @pytest.mark.asyncio
    async def test_unknown_event_type_returns_200_no_dispatch(self):
        a = make_adapter(verification_token="")
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        body = {"type": "event_callback", "event": {"type": "bot_added"}, "token": ""}
        req = fake_aiohttp_request(body)
        resp = await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert resp.status == 200
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_v2_non_message_event_type_not_dispatched(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        body = {
            "schema": "2.0",
            "header": {"event_type": "im.chat.member.user.added_v1", "token": "vtoken-abc"},
            "event": {},
        }
        req = fake_aiohttp_request(body)
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_returns_200_for_valid_v1_event(self):
        a = make_adapter()
        req = fake_aiohttp_request(make_v1_body())
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_returns_200_for_valid_v2_event(self):
        a = make_adapter()
        req = fake_aiohttp_request(make_v2_body())
        resp = await a._handle_webhook(req)
        assert resp.status == 200


# ===========================================================================
# 8. _process_event_v2()
# ===========================================================================


class TestProcessEventV2:
    def _extract_event(self, body: dict) -> dict:
        return body.get("event") or {}

    @pytest.mark.asyncio
    async def test_text_dispatched(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body(text="Hello")))
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_text_stripped(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body(text="  hi  ")))
        await asyncio.sleep(0)
        assert msgs[0].text == "hi"

    @pytest.mark.asyncio
    async def test_non_text_message_type_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        await a._process_event_v2(self._extract_event(make_v2_body(message_type="image")))
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mtype", ["file", "audio", "video", "sticker", "interactive"])
    async def test_various_non_text_types_dropped(self, mtype):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {
            "sender": {"sender_id": {"open_id": "ou_1"}, "sender_type": "user"},
            "message": {"message_type": mtype, "content": "{}", "chat_id": "oc_1",
                        "create_time": "1700000000000"},
        }
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_empty_text_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        body = make_v2_body(text="")
        event = body["event"]
        event["message"]["content"] = json.dumps({"text": ""})
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_whitespace_text_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        body = make_v2_body()
        event = body["event"]
        event["message"]["content"] = json.dumps({"text": "   "})
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_bot_open_id_echo_dropped(self):
        a = make_adapter(bot_open_id="ou_bot999")
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        await a._process_event_v2(self._extract_event(make_v2_body(open_id="ou_bot999")))
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_other_user_not_dropped(self):
        a = make_adapter(bot_open_id="ou_bot999")
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body(open_id="ou_other")))
        await asyncio.sleep(0)
        assert len(msgs) == 1

    @pytest.mark.asyncio
    async def test_sender_id_from_open_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body(open_id="ou_target")))
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "ou_target"

    @pytest.mark.asyncio
    async def test_thread_id_from_chat_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body(chat_id="oc_chat999")))
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "oc_chat999"

    @pytest.mark.asyncio
    async def test_thread_id_falls_back_to_open_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {
            "sender": {"sender_id": {"open_id": "ou_abc"}, "sender_type": "user"},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hi"}),
                "create_time": "1700000000000",
            },
        }
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "ou_abc"

    @pytest.mark.asyncio
    async def test_channel_is_feishu(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body()))
        await asyncio.sleep(0)
        assert msgs[0].channel == "feishu"

    @pytest.mark.asyncio
    async def test_timestamp_converted_from_ms(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body(create_time="1700000000000")))
        await asyncio.sleep(0)
        assert abs(msgs[0].timestamp - 1_700_000_000.0) < 0.001

    @pytest.mark.asyncio
    async def test_raw_event_preserved(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        body = make_v2_body()
        event = body["event"]
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        assert msgs[0].raw is event

    @pytest.mark.asyncio
    async def test_malformed_content_json_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {
            "sender": {"sender_id": {"open_id": "ou_1"}, "sender_type": "user"},
            "message": {
                "message_type": "text",
                "content": "not-valid-json",
                "chat_id": "oc_1",
                "create_time": "1700000000000",
            },
        }
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_missing_sender_uses_unknown(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "hi"}),
                "chat_id": "oc_1",
                "create_time": "1700000000000",
            },
        }
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "unknown"

    @pytest.mark.asyncio
    async def test_missing_message_key_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        await a._process_event_v2({"sender": {"sender_id": {"open_id": "ou_1"}}})
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_unicode_text(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(self._extract_event(make_v2_body(text="飞书测试消息")))
        await asyncio.sleep(0)
        assert msgs[0].text == "飞书测试消息"

    @pytest.mark.asyncio
    async def test_no_handler_does_not_raise(self):
        a = make_adapter()
        await a._process_event_v2(make_v2_body()["event"])
        await asyncio.sleep(0)


# ===========================================================================
# 9. _process_event_v1()
# ===========================================================================


class TestProcessEventV1:
    @pytest.mark.asyncio
    async def test_text_dispatched(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v1(make_v1_body()["event"])
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello!"

    @pytest.mark.asyncio
    async def test_empty_text_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {**make_v1_body()["event"], "text": ""}
        await a._process_event_v1(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_whitespace_text_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {**make_v1_body()["event"], "text": "   "}
        await a._process_event_v1(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_bot_open_id_echo_dropped(self):
        a = make_adapter(bot_open_id="ou_bot000")
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {**make_v1_body()["event"], "open_id": "ou_bot000"}
        await a._process_event_v1(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_sender_id_from_open_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {**make_v1_body()["event"], "open_id": "ou_v1_user"}
        await a._process_event_v1(event)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "ou_v1_user"

    @pytest.mark.asyncio
    async def test_thread_id_from_open_chat_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {**make_v1_body()["event"], "open_chat_id": "oc_v1_chat"}
        await a._process_event_v1(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "oc_v1_chat"

    @pytest.mark.asyncio
    async def test_thread_id_falls_back_to_open_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {"text": "hi", "open_id": "ou_fallback"}
        await a._process_event_v1(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "ou_fallback"

    @pytest.mark.asyncio
    async def test_channel_is_feishu(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v1(make_v1_body()["event"])
        await asyncio.sleep(0)
        assert msgs[0].channel == "feishu"

    @pytest.mark.asyncio
    async def test_missing_open_id_uses_unknown(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v1({"text": "hello"})
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "unknown"

    @pytest.mark.asyncio
    async def test_raw_event_preserved(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = make_v1_body()["event"]
        await a._process_event_v1(event)
        await asyncio.sleep(0)
        assert msgs[0].raw is event


# ===========================================================================
# 10. _get_access_token()
# ===========================================================================


class TestGetAccessToken:
    _TOKEN_RESP = {"code": 0, "msg": "ok", "tenant_access_token": "t-xyz", "expire": 7200}

    @pytest.mark.asyncio
    async def test_no_app_id_returns_none(self):
        a = make_adapter(app_id="")
        result = await a._get_access_token()
        assert result is None

    @pytest.mark.asyncio
    async def test_no_app_secret_returns_none(self):
        a = make_adapter(app_secret="")
        result = await a._get_access_token()
        assert result is None

    @pytest.mark.asyncio
    async def test_success_returns_token(self):
        a = make_adapter()
        resp = fake_response(200, self._TOKEN_RESP)
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a._get_access_token()
        assert result == "t-xyz"

    @pytest.mark.asyncio
    async def test_token_cached_after_fetch(self):
        a = make_adapter()
        resp = fake_response(200, self._TOKEN_RESP)
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
            await a._get_access_token()
        assert client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_miss_on_expired_token(self):
        a = make_adapter()
        resp = fake_response(200, self._TOKEN_RESP)
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
            a._token_expiry = time.time() - 1  # force expiry
            await a._get_access_token()
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        a = make_adapter()
        resp = fake_response(500, {})
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a._get_access_token()
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("no route"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a._get_access_token()
        assert result is None

    @pytest.mark.asyncio
    async def test_non_zero_code_returns_none(self):
        a = make_adapter()
        resp = fake_response(200, {"code": 99991663, "msg": "app not found"})
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a._get_access_token()
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_correct_url(self):
        a = make_adapter()
        resp = fake_response(200, self._TOKEN_RESP)
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        assert client.post.call_args[0][0] == _TOKEN_URL

    @pytest.mark.asyncio
    async def test_payload_includes_credentials(self):
        a = make_adapter()
        resp = fake_response(200, self._TOKEN_RESP)
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        payload = client.post.call_args[1]["json"]
        assert payload["app_id"] == "cli_test123"
        assert payload["app_secret"] == "test-secret"


# ===========================================================================
# 11. send()
# ===========================================================================


_SEND_RESP = {"code": 0, "msg": "success", "data": {"message_id": "om_msg999"}}


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        a = make_adapter()
        result = await a.send("", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        a = make_adapter(app_id="", app_secret="")
        result = await a.send("ou_abc", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_success_returns_message_id(self):
        a = make_adapter()
        resp = fake_response(200, _SEND_RESP)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok-123")),
            patch("httpx.AsyncClient", return_value=fake_client(resp)),
        ):
            result = await a.send("ou_abc", "hello")
        assert result == "om_msg999"

    @pytest.mark.asyncio
    async def test_uses_send_url(self):
        a = make_adapter()
        resp = fake_response(200, _SEND_RESP)
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.send("ou_abc", "hi")
        assert client.post.call_args[0][0] == _SEND_URL

    @pytest.mark.asyncio
    async def test_payload_structure(self):
        a = make_adapter()
        resp = fake_response(200, _SEND_RESP)
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.send("ou_abc", "test text")
        payload = client.post.call_args[1]["json"]
        assert payload["receive_id"] == "ou_abc"
        assert payload["msg_type"] == "text"
        content = json.loads(payload["content"])
        assert content["text"] == "test text"

    @pytest.mark.asyncio
    async def test_auth_header(self):
        a = make_adapter()
        resp = fake_response(200, _SEND_RESP)
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok-xyz")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.send("ou_abc", "hi")
        headers = client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer tok-xyz"

    @pytest.mark.asyncio
    async def test_receive_id_type_in_params(self):
        a = make_adapter(receive_id_type="chat_id")
        resp = fake_response(200, _SEND_RESP)
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.send("oc_chat", "hi")
        params = client.post.call_args[1]["params"]
        assert params["receive_id_type"] == "chat_id"

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        a = make_adapter()
        resp = fake_response(400, {})
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=fake_client(resp)),
        ):
            result = await a.send("ou_abc", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            result = await a.send("ou_abc", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_non_zero_api_code_returns_none(self):
        a = make_adapter()
        resp = fake_response(200, {"code": 230002, "msg": "user not found"})
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=fake_client(resp)),
        ):
            result = await a.send("ou_abc", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_is_15s(self):
        a = make_adapter()
        resp = fake_response(200, _SEND_RESP)
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.send("ou_abc", "hi")
        assert client.post.call_args[1]["timeout"] == 15.0

    @pytest.mark.asyncio
    async def test_unicode_text_in_content(self):
        a = make_adapter()
        resp = fake_response(200, _SEND_RESP)
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.send("ou_abc", "你好世界")
        content = json.loads(client.post.call_args[1]["json"]["content"])
        assert content["text"] == "你好世界"

    @pytest.mark.asyncio
    async def test_token_fetch_failure_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value=None)):
            result = await a.send("ou_abc", "hi")
        assert result is None


# ===========================================================================
# 12. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_false(self):
        a = make_adapter(app_id="", app_secret="")
        result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_token_fetch_failure_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value=None)):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_success_code_0_returns_true(self):
        a = make_adapter()
        resp = fake_response(200, {"code": 0, "data": {"bot_info": {}}})
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=fake_client(resp)),
        ):
            result = await a.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_non_zero_code_returns_false(self):
        a = make_adapter()
        resp = fake_response(200, {"code": 99991663, "msg": "error"})
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=fake_client(resp)),
        ):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_http_error_returns_false(self):
        a = make_adapter()
        resp = fake_response(401, {})
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=fake_client(resp)),
        ):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_uses_bot_info_url(self):
        a = make_adapter()
        resp = fake_response(200, {"code": 0})
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.ping()
        assert client.get.call_args[0][0] == _BOT_INFO_URL

    @pytest.mark.asyncio
    async def test_auth_header_on_ping(self):
        a = make_adapter()
        resp = fake_response(200, {"code": 0})
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok-ping")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.ping()
        assert client.get.call_args[1]["headers"]["Authorization"] == "Bearer tok-ping"

    @pytest.mark.asyncio
    async def test_timeout_is_5s(self):
        a = make_adapter()
        resp = fake_response(200, {"code": 0})
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.ping()
        assert client.get.call_args[1]["timeout"] == 5.0


# ===========================================================================
# 13. get_config_schema()
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

    def test_properties_has_app_id(self):
        assert "app_id" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_app_secret(self):
        assert "app_secret" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_verification_token(self):
        assert "verification_token" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_host(self):
        assert "host" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_port(self):
        assert "port" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_webhook_path(self):
        assert "webhook_path" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_bot_open_id(self):
        assert "bot_open_id" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_receive_id_type(self):
        assert "receive_id_type" in make_adapter().get_config_schema()["properties"]

    def test_port_default(self):
        assert make_adapter().get_config_schema()["properties"]["port"]["default"] == 8087

    def test_host_default(self):
        assert make_adapter().get_config_schema()["properties"]["host"]["default"] == "0.0.0.0"

    def test_webhook_path_default(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["webhook_path"]["default"] == "/webhook/feishu"

    def test_receive_id_type_default(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["receive_id_type"]["default"] == "open_id"

    def test_receive_id_type_enum(self):
        schema = make_adapter().get_config_schema()
        enum = schema["properties"]["receive_id_type"]["enum"]
        assert set(enum) == {"open_id", "chat_id", "user_id", "union_id"}


# ===========================================================================
# 14. Constants
# ===========================================================================


class TestConstants:
    def test_feishu_api_base(self):
        assert _FEISHU_API == "https://open.feishu.cn/open-apis"

    def test_token_url(self):
        assert "tenant_access_token" in _TOKEN_URL
        assert _TOKEN_URL.startswith("https://open.feishu.cn")

    def test_send_url(self):
        assert "im/v1/messages" in _SEND_URL

    def test_bot_info_url(self):
        assert "bot/v3/info" in _BOT_INFO_URL


# ===========================================================================
# 15. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "feishu" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_send_default_receive_id_type_is_open_id(self):
        a = make_adapter()
        resp = fake_response(200, _SEND_RESP)
        client = fake_client(resp)
        with (
            patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")),
            patch("httpx.AsyncClient", return_value=client),
        ):
            await a.send("ou_abc", "hi")
        params = client.post.call_args[1]["params"]
        assert params["receive_id_type"] == "open_id"

    @pytest.mark.asyncio
    async def test_v2_missing_create_time_falls_back_to_now(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        before = time.time()
        event = {
            "sender": {"sender_id": {"open_id": "ou_1"}, "sender_type": "user"},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": "no ts"}),
                "chat_id": "oc_1",
            },
        }
        await a._process_event_v2(event)
        await asyncio.sleep(0)
        after = time.time()
        assert before - 0.01 <= msgs[0].timestamp <= after + 1

    @pytest.mark.asyncio
    async def test_bot_open_id_empty_all_users_accepted(self):
        a = make_adapter(bot_open_id="")
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event_v2(make_v2_body(open_id="ou_botid")["event"])
        await asyncio.sleep(0)
        assert len(msgs) == 1

    @pytest.mark.asyncio
    async def test_full_v2_flow_via_webhook(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        req = fake_aiohttp_request(make_v2_body(text="end-to-end"))
        resp = await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert resp.status == 200
        assert len(msgs) == 1
        assert msgs[0].text == "end-to-end"
        assert msgs[0].channel == "feishu"

    @pytest.mark.asyncio
    async def test_full_v1_flow_via_webhook(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        req = fake_aiohttp_request(make_v1_body(text="v1-end-to-end"))
        resp = await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert resp.status == 200
        assert len(msgs) == 1
        assert msgs[0].text == "v1-end-to-end"
