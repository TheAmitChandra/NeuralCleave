"""Unit tests for neuralcleave.channels.line — LineAdapter.

Covers:
  - Construction / config parsing / defaults
  - is_connected lifecycle (before/after connect/disconnect)
  - connect() / disconnect() — server setup, teardown, double-disconnect safety
  - _verify_signature() — correct / wrong / empty / no-secret cases
  - _handle_webhook() — valid payload, bad sig, bad JSON, event routing
  - _handle_health() — GET endpoint
  - _process_event() — message vs non-message; text vs non-text; source types;
    echo prevention; timestamp conversion; missing fields; dispatch
  - send() — success, no token, empty target, HTTP errors, network errors,
    payload structure, auth header, return value
  - ping() — success, failure, no token, network errors
  - get_config_schema() — shape and required fields
  - Edge cases — whitespace text, unicode, long text, unknown source types
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.line import (
    _INFO_URL,
    _LINE_API_BASE,
    _PUSH_URL,
    LineAdapter,
)

# ===========================================================================
# Helpers / fixtures
# ===========================================================================


def make_adapter(**overrides: Any) -> LineAdapter:
    cfg: dict[str, Any] = {
        "channel_access_token": "test-token",
        "channel_secret": "test-secret",
        **overrides,
    }
    return LineAdapter(cfg)


def make_text_event(
    text: str = "Hello!",
    user_id: str = "Uabc123",
    source_type: str = "user",
    group_id: str | None = None,
    room_id: str | None = None,
    timestamp: int = 1_700_000_000_000,
) -> dict[str, Any]:
    source: dict[str, Any] = {"type": source_type, "userId": user_id}
    if group_id:
        source["groupId"] = group_id
    if room_id:
        source["roomId"] = room_id
    return {
        "type": "message",
        "message": {"type": "text", "id": "msg-001", "text": text},
        "source": source,
        "timestamp": timestamp,
        "replyToken": "reply-token-001",
        "mode": "active",
    }


def make_webhook_body(events: list[dict]) -> bytes:
    return json.dumps({"destination": "Ubot123", "events": events}).encode()


def make_signature(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(mac).decode()


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


def fake_aiohttp_request(
    body: bytes,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    req = MagicMock()
    req.read = AsyncMock(return_value=body)
    req.headers = headers or {}
    return req


# ===========================================================================
# 1. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_token_empty(self):
        a = LineAdapter({})
        assert a._token == ""

    def test_default_secret_empty(self):
        a = LineAdapter({})
        assert a._secret == ""

    def test_default_host(self):
        assert make_adapter()._host == "0.0.0.0"

    def test_default_port(self):
        assert make_adapter()._port == 8086

    def test_default_webhook_path(self):
        assert make_adapter()._webhook_path == "/webhook/line"

    def test_default_bot_user_id_empty(self):
        assert make_adapter()._bot_user_id == ""

    def test_default_runner_none(self):
        assert make_adapter()._runner is None

    def test_custom_token(self):
        assert make_adapter(channel_access_token="tok-xyz")._token == "tok-xyz"

    def test_custom_secret(self):
        assert make_adapter(channel_secret="sec-abc")._secret == "sec-abc"

    def test_custom_host(self):
        assert make_adapter(host="127.0.0.1")._host == "127.0.0.1"

    def test_custom_port_int(self):
        assert make_adapter(port=9000)._port == 9000

    def test_custom_port_string_coerced(self):
        assert make_adapter(port="9001")._port == 9001

    def test_custom_webhook_path(self):
        assert make_adapter(webhook_path="/line/hook")._webhook_path == "/line/hook"

    def test_custom_bot_user_id(self):
        assert make_adapter(bot_user_id="Ubot999")._bot_user_id == "Ubot999"

    def test_channel_id(self):
        assert LineAdapter.channel_id == "line"

    def test_channel_id_on_instance(self):
        assert make_adapter().channel_id == "line"

    def test_empty_config(self):
        a = LineAdapter({})
        assert a._token == ""
        assert a._secret == ""
        assert a._port == 8086


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
        mock_app = MagicMock()

        with (
            patch("neuralcleave.channels.line.LineAdapter._handle_webhook"),
            patch("neuralcleave.channels.line.LineAdapter._handle_health"),
            patch("aiohttp.web.Application", return_value=mock_app),
            patch("aiohttp.web.AppRunner", return_value=mock_runner),
            patch("aiohttp.web.TCPSite", return_value=mock_site),
        ):
            await a.connect()

        assert a._runner is mock_runner

    @pytest.mark.asyncio
    async def test_connect_calls_runner_setup(self):
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
        mock_runner = AsyncMock()
        a._runner = mock_runner
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
    async def test_disconnect_when_not_connected_safe(self):
        a = make_adapter()
        await a.disconnect()  # should not raise
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_double_disconnect_safe(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        a._runner = mock_runner
        await a.disconnect()
        await a.disconnect()  # second call — runner already None
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_is_connected_false_after_disconnect(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        assert not a.is_connected


# ===========================================================================
# 4. _verify_signature()
# ===========================================================================


class TestVerifySignature:
    def _sig(self, body: bytes, secret: str = "test-secret") -> str:
        return make_signature(body, secret)

    def test_valid_signature_returns_true(self):
        a = make_adapter(channel_secret="test-secret")
        body = b'{"events":[]}'
        assert a._verify_signature(body, self._sig(body)) is True

    def test_wrong_signature_returns_false(self):
        a = make_adapter(channel_secret="test-secret")
        body = b'{"events":[]}'
        assert a._verify_signature(body, "wrong-sig") is False

    def test_empty_signature_returns_false(self):
        a = make_adapter(channel_secret="test-secret")
        body = b'{"events":[]}'
        assert a._verify_signature(body, "") is False

    def test_no_secret_configured_returns_false(self):
        a = make_adapter(channel_secret="")
        body = b'{"events":[]}'
        sig = self._sig(body)
        assert a._verify_signature(body, sig) is False

    def test_tampered_body_returns_false(self):
        a = make_adapter(channel_secret="test-secret")
        body = b'{"events":[]}'
        sig = self._sig(body)
        tampered = b'{"events":[{}]}'
        assert a._verify_signature(tampered, sig) is False

    def test_different_secret_returns_false(self):
        a = make_adapter(channel_secret="secret-A")
        body = b'{"events":[]}'
        sig = self._sig(body, "secret-B")
        assert a._verify_signature(body, sig) is False

    def test_empty_body_with_correct_sig(self):
        a = make_adapter(channel_secret="test-secret")
        body = b""
        assert a._verify_signature(body, self._sig(body)) is True

    def test_unicode_secret(self):
        secret = "秘密"
        a = make_adapter(channel_secret=secret)
        body = b"hello"
        assert a._verify_signature(body, self._sig(body, secret)) is True

    def test_binary_body(self):
        a = make_adapter(channel_secret="test-secret")
        body = bytes(range(256))
        assert a._verify_signature(body, self._sig(body)) is True

    def test_large_body(self):
        a = make_adapter(channel_secret="test-secret")
        body = b"x" * 100_000
        assert a._verify_signature(body, self._sig(body)) is True

    def test_constant_time_compare_used(self):
        a = make_adapter(channel_secret="test-secret")
        body = b"data"
        correct_sig = self._sig(body)
        flipped = correct_sig[:-1] + ("A" if correct_sig[-1] != "A" else "B")
        assert a._verify_signature(body, flipped) is False


# ===========================================================================
# 5. _handle_health()
# ===========================================================================


class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        from aiohttp.web import Response
        a = make_adapter()
        req = MagicMock()
        resp = await a._handle_health(req)
        assert isinstance(resp, Response)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_health_body(self):
        a = make_adapter()
        req = MagicMock()
        resp = await a._handle_health(req)
        assert b"LINE" in resp.body or b"OK" in resp.body


# ===========================================================================
# 6. _handle_webhook()
# ===========================================================================


class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_valid_request_returns_200(self):
        a = make_adapter()
        body = make_webhook_body([])
        sig = make_signature(body, "test-secret")
        req = fake_aiohttp_request(body, {"X-Line-Signature": sig})
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_bad_signature_returns_400(self):
        a = make_adapter()
        body = make_webhook_body([])
        req = fake_aiohttp_request(body, {"X-Line-Signature": "bad-sig"})
        resp = await a._handle_webhook(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_no_signature_header_with_secret_returns_400(self):
        a = make_adapter()
        body = make_webhook_body([])
        req = fake_aiohttp_request(body, {})
        resp = await a._handle_webhook(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_no_secret_configured_skips_sig_check(self):
        a = make_adapter(channel_secret="")
        body = make_webhook_body([])
        req = fake_aiohttp_request(body, {})
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        a = make_adapter(channel_secret="")
        req = fake_aiohttp_request(b"not-json", {})
        resp = await a._handle_webhook(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_empty_events_list_returns_200(self):
        a = make_adapter(channel_secret="")
        body = make_webhook_body([])
        req = fake_aiohttp_request(body, {})
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_missing_events_key_returns_200(self):
        a = make_adapter(channel_secret="")
        body = json.dumps({"destination": "Ubot"}).encode()
        req = fake_aiohttp_request(body, {})
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_dispatches_message_event(self):
        a = make_adapter(channel_secret="")
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        event = make_text_event(text="Hi there")
        body = make_webhook_body([event])
        req = fake_aiohttp_request(body, {})
        await a._handle_webhook(req)
        await asyncio.sleep(0)  # let create_task run
        assert len(dispatched) == 1
        assert dispatched[0].text == "Hi there"

    @pytest.mark.asyncio
    async def test_ignores_non_message_event(self):
        a = make_adapter(channel_secret="")
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        follow_event = {"type": "follow", "source": {"type": "user", "userId": "Uabc"}}
        body = make_webhook_body([follow_event])
        req = fake_aiohttp_request(body, {})
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(dispatched) == 0

    @pytest.mark.asyncio
    async def test_multiple_events_all_dispatched(self):
        a = make_adapter(channel_secret="")
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        events = [make_text_event(text="A"), make_text_event(text="B")]
        body = make_webhook_body(events)
        req = fake_aiohttp_request(body, {})
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(dispatched) == 2

    @pytest.mark.asyncio
    async def test_mixed_events_only_message_dispatched(self):
        a = make_adapter(channel_secret="")
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        events = [
            {"type": "follow", "source": {"type": "user", "userId": "U1"}},
            make_text_event(text="Hello"),
            {"type": "unfollow", "source": {"type": "user", "userId": "U2"}},
        ]
        body = make_webhook_body(events)
        req = fake_aiohttp_request(body, {})
        await a._handle_webhook(req)
        await asyncio.sleep(0)
        assert len(dispatched) == 1
        assert dispatched[0].text == "Hello"


# ===========================================================================
# 7. _process_event()
# ===========================================================================


class TestProcessEvent:
    @pytest.mark.asyncio
    async def test_text_message_dispatched(self):
        a = make_adapter()
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(text="Hello"))
        await asyncio.sleep(0)
        assert len(dispatched) == 1

    @pytest.mark.asyncio
    async def test_text_preserved(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_event(make_text_event(text="  trimmed  "))
        await asyncio.sleep(0)
        assert msgs[0].text == "trimmed"

    @pytest.mark.asyncio
    async def test_non_message_event_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        for etype in ("follow", "unfollow", "join", "leave", "postback", "beacon",
                      "memberJoined", "memberLeft", "things"):
            await a._process_event({"type": etype})
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_image_message_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {
            "type": "message",
            "message": {"type": "image", "id": "img-001"},
            "source": {"type": "user", "userId": "Uabc"},
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_sticker_message_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {
            "type": "message",
            "message": {"type": "sticker", "id": "sticker-001"},
            "source": {"type": "user", "userId": "Uabc"},
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mtype", ["video", "audio", "location", "file", "template", "flex"])
    async def test_non_text_message_types_dropped(self, mtype):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {
            "type": "message",
            "message": {"type": mtype},
            "source": {"type": "user", "userId": "Uabc"},
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_empty_text_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        await a._process_event(make_text_event(text=""))
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_whitespace_only_text_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        await a._process_event(make_text_event(text="   "))
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_none_text_dropped(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        event = {
            "type": "message",
            "message": {"type": "text", "text": None},
            "source": {"type": "user", "userId": "Uabc"},
            "timestamp": 1700000000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_bot_user_id_echo_dropped(self):
        a = make_adapter(bot_user_id="Ubot123")
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        await a._process_event(make_text_event(user_id="Ubot123", text="echo"))
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_bot_user_id_empty_accepts_all(self):
        a = make_adapter(bot_user_id="")
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(user_id="Ubot123", text="not dropped"))
        await asyncio.sleep(0)
        assert len(dispatched) == 1

    @pytest.mark.asyncio
    async def test_other_user_not_bot_passes(self):
        a = make_adapter(bot_user_id="Ubot000")
        dispatched: list = []

        async def handler(msg):
            dispatched.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(user_id="Uuser999", text="hi"))
        await asyncio.sleep(0)
        assert len(dispatched) == 1

    @pytest.mark.asyncio
    async def test_user_source_thread_id_is_user_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event(
            make_text_event(user_id="Uabc", source_type="user")
        )
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "Uabc"

    @pytest.mark.asyncio
    async def test_group_source_thread_id_is_group_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = make_text_event(user_id="Uabc", source_type="group", group_id="Cgroup1")
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "Cgroup1"

    @pytest.mark.asyncio
    async def test_room_source_thread_id_is_room_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = make_text_event(user_id="Uabc", source_type="room", room_id="Rroom1")
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "Rroom1"

    @pytest.mark.asyncio
    async def test_unknown_source_type_defaults_to_user_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {
            "type": "message",
            "message": {"type": "text", "text": "hi"},
            "source": {"type": "mystery", "userId": "Umystery"},
            "timestamp": 1700000000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "Umystery"

    @pytest.mark.asyncio
    async def test_missing_user_id_uses_unknown(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {
            "type": "message",
            "message": {"type": "text", "text": "hi"},
            "source": {"type": "user"},
            "timestamp": 1700000000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "unknown"

    @pytest.mark.asyncio
    async def test_sender_id_from_user_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(user_id="Uuser42"))
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "Uuser42"

    @pytest.mark.asyncio
    async def test_sender_name_equals_sender_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(user_id="Uabc"))
        await asyncio.sleep(0)
        assert msgs[0].sender_name == "Uabc"

    @pytest.mark.asyncio
    async def test_channel_is_line(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event())
        await asyncio.sleep(0)
        assert msgs[0].channel == "line"

    @pytest.mark.asyncio
    async def test_timestamp_converted_from_ms_to_seconds(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(timestamp=1_700_000_000_000))
        await asyncio.sleep(0)
        assert abs(msgs[0].timestamp - 1_700_000_000.0) < 0.001

    @pytest.mark.asyncio
    async def test_missing_timestamp_falls_back_to_now(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        before = time.time()
        event = {
            "type": "message",
            "message": {"type": "text", "text": "hi"},
            "source": {"type": "user", "userId": "Uabc"},
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        after = time.time()
        assert before - 0.01 <= msgs[0].timestamp <= after + 1

    @pytest.mark.asyncio
    async def test_raw_event_preserved(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = make_text_event(text="raw check")
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].raw is event

    @pytest.mark.asyncio
    async def test_missing_source_key_uses_defaults(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {
            "type": "message",
            "message": {"type": "text", "text": "no source"},
            "timestamp": 1700000000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "unknown"

    @pytest.mark.asyncio
    async def test_missing_message_key_does_not_raise(self):
        a = make_adapter()
        dispatched: list = []
        a.on_message(lambda m: dispatched.append(m))
        await a._process_event({"type": "message", "source": {"type": "user", "userId": "U1"}})
        await asyncio.sleep(0)
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_unicode_text_dispatched(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(text="日本語テスト"))
        await asyncio.sleep(0)
        assert msgs[0].text == "日本語テスト"

    @pytest.mark.asyncio
    async def test_emoji_text_dispatched(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        await a._process_event(make_text_event(text="Hello 🎉"))
        await asyncio.sleep(0)
        assert msgs[0].text == "Hello 🎉"

    @pytest.mark.asyncio
    async def test_no_handler_does_not_raise(self):
        a = make_adapter()
        await a._process_event(make_text_event())
        await asyncio.sleep(0)


# ===========================================================================
# 8. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_send_no_token_returns_none(self):
        a = make_adapter(channel_access_token="")
        result = await a.send("Uabc", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_empty_target_returns_none(self):
        a = make_adapter()
        result = await a.send("", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_success_returns_target(self):
        a = make_adapter()
        resp = fake_response(200, {})
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.send("Uabc123", "Hello!")
        assert result == "Uabc123"

    @pytest.mark.asyncio
    async def test_send_uses_push_url(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("Uabc", "hi")
        client.post.assert_awaited_once()
        call_args = client.post.call_args
        assert call_args[0][0] == _PUSH_URL

    @pytest.mark.asyncio
    async def test_send_payload_structure(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("Uabc", "test text")
        payload = client.post.call_args[1]["json"]
        assert payload["to"] == "Uabc"
        assert payload["messages"] == [{"type": "text", "text": "test text"}]

    @pytest.mark.asyncio
    async def test_send_auth_header(self):
        a = make_adapter(channel_access_token="my-token-xyz")
        resp = fake_response(200, {})
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("Uabc", "hi")
        headers = client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer my-token-xyz"

    @pytest.mark.asyncio
    async def test_send_content_type_header(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("Uabc", "hi")
        headers = client.post.call_args[1]["headers"]
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_send_http_error_returns_none(self):
        a = make_adapter()
        resp = fake_response(400, {})
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.send("Uabc", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_network_error_returns_none(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("timeout"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a.send("Uabc", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_group_target(self):
        a = make_adapter()
        resp = fake_response(200, {})
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.send("Cgroup123", "group message")
        assert result == "Cgroup123"

    @pytest.mark.asyncio
    async def test_send_room_target(self):
        a = make_adapter()
        resp = fake_response(200, {})
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.send("Rroom456", "room message")
        assert result == "Rroom456"

    @pytest.mark.asyncio
    async def test_send_unicode_text(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("Uabc", "こんにちは世界")
        payload = client.post.call_args[1]["json"]
        assert payload["messages"][0]["text"] == "こんにちは世界"

    @pytest.mark.asyncio
    async def test_send_401_returns_none(self):
        a = make_adapter()
        resp = fake_response(401, {})
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.send("Uabc", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_timeout_15s(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("Uabc", "hi")
        assert client.post.call_args[1]["timeout"] == 15.0


# ===========================================================================
# 9. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_ping_no_token_returns_false(self):
        a = make_adapter(channel_access_token="")
        result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_success_returns_true(self):
        a = make_adapter()
        resp = fake_response(200)
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_401_returns_false(self):
        a = make_adapter()
        resp = fake_response(401)
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_404_returns_false(self):
        a = make_adapter()
        resp = fake_response(404)
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_network_error_returns_false(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("no route"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_uses_info_url(self):
        a = make_adapter()
        resp = fake_response(200)
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        client.get.assert_awaited_once()
        assert client.get.call_args[0][0] == _INFO_URL

    @pytest.mark.asyncio
    async def test_ping_auth_header(self):
        a = make_adapter(channel_access_token="ping-token")
        resp = fake_response(200)
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        headers = client.get.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer ping-token"

    @pytest.mark.asyncio
    async def test_ping_timeout_5s(self):
        a = make_adapter()
        resp = fake_response(200)
        client = fake_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        assert client.get.call_args[1]["timeout"] == 5.0

    @pytest.mark.asyncio
    async def test_ping_500_returns_false(self):
        a = make_adapter()
        resp = fake_response(500)
        with patch("httpx.AsyncClient", return_value=fake_client(resp)):
            result = await a.ping()
        assert result is False


# ===========================================================================
# 10. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_includes_token(self):
        assert "channel_access_token" in make_adapter().get_config_schema()["required"]

    def test_required_includes_secret(self):
        assert "channel_secret" in make_adapter().get_config_schema()["required"]

    def test_properties_has_channel_access_token(self):
        assert "channel_access_token" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_channel_secret(self):
        assert "channel_secret" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_host(self):
        assert "host" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_port(self):
        assert "port" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_webhook_path(self):
        assert "webhook_path" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_bot_user_id(self):
        assert "bot_user_id" in make_adapter().get_config_schema()["properties"]

    def test_host_default_value(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["host"]["default"] == "0.0.0.0"

    def test_port_default_value(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["port"]["default"] == 8086

    def test_webhook_path_default_value(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["webhook_path"]["default"] == "/webhook/line"

    def test_port_type_is_integer(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["port"]["type"] == "integer"


# ===========================================================================
# 11. Constants
# ===========================================================================


class TestConstants:
    def test_push_url(self):
        assert "api.line.me" in _PUSH_URL
        assert "message/push" in _PUSH_URL

    def test_info_url(self):
        assert "api.line.me" in _INFO_URL
        assert "info" in _INFO_URL

    def test_line_api_base(self):
        assert _LINE_API_BASE == "https://api.line.me/v2/bot"


# ===========================================================================
# 12. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_group_event_no_group_id_falls_back_to_user_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {
            "type": "message",
            "message": {"type": "text", "text": "group no id"},
            "source": {"type": "group", "userId": "Uabc"},
            "timestamp": 1700000000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "Uabc"

    @pytest.mark.asyncio
    async def test_room_event_no_room_id_falls_back_to_user_id(self):
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        event = {
            "type": "message",
            "message": {"type": "text", "text": "room no id"},
            "source": {"type": "room", "userId": "Uabc"},
            "timestamp": 1700000000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "Uabc"

    @pytest.mark.asyncio
    async def test_signature_correct_but_no_secret_rejects(self):
        a = make_adapter(channel_secret="")
        body = make_webhook_body([])
        sig = make_signature(body, "some-secret")
        assert a._verify_signature(body, sig) is False

    def test_repr_contains_channel_id(self):
        assert "line" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_send_long_text(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_client(resp)
        long_text = "A" * 5000
        with patch("httpx.AsyncClient", return_value=client):
            result = await a.send("Uabc", long_text)
        assert result == "Uabc"
        payload = client.post.call_args[1]["json"]
        assert payload["messages"][0]["text"] == long_text

    @pytest.mark.asyncio
    async def test_process_event_does_not_dispatch_without_handler(self):
        a = make_adapter()
        event = make_text_event()
        await a._process_event(event)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_webhook_handler_returns_ok_body(self):
        a = make_adapter(channel_secret="")
        body = make_webhook_body([])
        req = fake_aiohttp_request(body, {})
        resp = await a._handle_webhook(req)
        assert resp.status == 200
        assert b"OK" in resp.body
