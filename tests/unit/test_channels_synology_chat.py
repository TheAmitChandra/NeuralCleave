"""Unit tests for neuralcleave.channels.synology_chat — SynologyChatAdapter.

Covers:
  - Constructor / defaults / config parsing
  - is_connected lifecycle
  - connect() / disconnect()
  - _build_payload() — user, channel, bare int, invalid
  - _handle_webhook() — token verification, text dispatch, bot echo guard,
    empty text, bad form data, field parsing
  - _handle_health() — GET endpoint
  - send() — user target, channel target, bare int, empty target,
    missing credentials, API success/failure, network error
  - ping() — success, non-5xx, server error, network error, no credentials
  - get_config_schema() — shape and required fields
  - Constants
  - Edge / integration cases
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.synology_chat import (
    _SYNO_API,
    _SYNO_API_PATH,
    _SYNO_METHOD,
    _SYNO_VERSION,
    SynologyChatAdapter,
)

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def make_adapter(**overrides: Any) -> SynologyChatAdapter:
    cfg: dict[str, Any] = {
        "token": "out_token",
        "incoming_token": "in_token",
        "synology_url": "https://nas.example.com:5001",
        **overrides,
    }
    return SynologyChatAdapter(cfg)


def make_webhook_params(
    text: str = "Hello bot!",
    username: str = "alice",
    user_id: str = "42",
    channel_id: str = "7",
    channel_name: str = "general",
    token: str = "out_token",
    timestamp: str = "1700000000",
) -> dict[str, str]:
    return {
        "token": token,
        "text": text,
        "username": username,
        "user_id": user_id,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "timestamp": timestamp,
    }


def fake_form_request(params: dict[str, str]) -> MagicMock:
    req = MagicMock()
    req.post = AsyncMock(return_value=params)
    return req


def fake_bad_post_request() -> MagicMock:
    req = MagicMock()
    req.post = AsyncMock(side_effect=ValueError("bad form"))
    return req


def fake_response(
    status: int = 200, json_data: dict | None = None, raise_on_status: bool = False
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data or {})
    resp.raise_for_status = MagicMock()
    if raise_on_status or status >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def fake_http_client(response: MagicMock) -> MagicMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ===========================================================================
# 1. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_token_empty(self):
        assert SynologyChatAdapter({})._token == ""

    def test_default_incoming_token_empty(self):
        assert SynologyChatAdapter({})._incoming_token == ""

    def test_default_synology_url_empty(self):
        assert SynologyChatAdapter({})._synology_url == ""

    def test_default_host(self):
        assert make_adapter()._host == "0.0.0.0"

    def test_default_port(self):
        assert make_adapter()._port == 8089

    def test_default_webhook_path(self):
        assert make_adapter()._webhook_path == "/webhook/synology_chat"

    def test_default_bot_username_empty(self):
        assert make_adapter()._bot_username == ""

    def test_default_runner_none(self):
        assert make_adapter()._runner is None

    def test_custom_token(self):
        assert make_adapter(token="tok123")._token == "tok123"

    def test_custom_incoming_token(self):
        assert make_adapter(incoming_token="in_tok")._incoming_token == "in_tok"

    def test_custom_synology_url(self):
        a = make_adapter(synology_url="https://nas.local:5001/")
        assert a._synology_url == "https://nas.local:5001"

    def test_synology_url_trailing_slash_stripped(self):
        a = make_adapter(synology_url="https://nas.local:5001/")
        assert not a._synology_url.endswith("/")

    def test_custom_host(self):
        assert make_adapter(host="127.0.0.1")._host == "127.0.0.1"

    def test_custom_port_int(self):
        assert make_adapter(port=9000)._port == 9000

    def test_custom_port_string_coerced(self):
        assert make_adapter(port="9001")._port == 9001

    def test_custom_webhook_path(self):
        assert make_adapter(webhook_path="/syno")._webhook_path == "/syno"

    def test_custom_bot_username(self):
        assert make_adapter(bot_username="neuralcleavebot")._bot_username == "neuralcleavebot"

    def test_channel_id(self):
        assert SynologyChatAdapter.channel_id == "synology_chat"

    def test_channel_id_on_instance(self):
        assert make_adapter().channel_id == "synology_chat"


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


# ===========================================================================
# 4. _build_payload()
# ===========================================================================


class TestBuildPayload:
    def test_user_prefix_sends_to_user_ids(self):
        a = make_adapter()
        payload, err = a._build_payload("user:42", "hello")
        assert err is None
        assert payload == {"text": "hello", "user_ids": [42]}

    def test_channel_prefix_sends_to_channel_id(self):
        a = make_adapter()
        payload, err = a._build_payload("channel:7", "hello")
        assert err is None
        assert payload == {"text": "hello", "channel_id": 7}

    def test_bare_integer_string_as_user(self):
        a = make_adapter()
        payload, err = a._build_payload("99", "hi")
        assert err is None
        assert payload == {"text": "hi", "user_ids": [99]}

    def test_invalid_user_id_returns_error(self):
        a = make_adapter()
        payload, err = a._build_payload("user:abc", "hi")
        assert err is not None
        assert payload == {}

    def test_invalid_channel_id_returns_error(self):
        a = make_adapter()
        payload, err = a._build_payload("channel:xyz", "hi")
        assert err is not None
        assert payload == {}

    def test_non_numeric_bare_returns_error(self):
        a = make_adapter()
        payload, err = a._build_payload("alice", "hi")
        assert err is not None
        assert payload == {}

    def test_text_preserved_in_payload(self):
        a = make_adapter()
        payload, err = a._build_payload("user:1", "Unicode 🌸 text")
        assert err is None
        assert payload["text"] == "Unicode 🌸 text"

    def test_user_id_is_int_in_list(self):
        a = make_adapter()
        payload, _ = a._build_payload("user:123", "x")
        assert isinstance(payload["user_ids"][0], int)

    def test_channel_id_is_int(self):
        a = make_adapter()
        payload, _ = a._build_payload("channel:5", "x")
        assert isinstance(payload["channel_id"], int)


# ===========================================================================
# 5. _handle_webhook()
# ===========================================================================


class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_returns_200_on_valid_message(self):
        a = make_adapter()
        req = fake_form_request(make_webhook_params())
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self):
        a = make_adapter()
        params = make_webhook_params(token="bad_token")
        req = fake_form_request(params)
        resp = await a._handle_webhook(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_no_token_configured_accepts_all(self):
        a = make_adapter(token="")
        params = make_webhook_params(token="anything")
        req = fake_form_request(params)
        resp = await a._handle_webhook(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_empty_text_returns_200_no_dispatch(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_webhook_params(text="")
        req = fake_form_request(params)
        resp = await a._handle_webhook(req)
        assert resp.status == 200
        import asyncio
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_whitespace_text_not_dispatched(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_webhook_params(text="   ")
        req = fake_form_request(params)
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_bot_username_echo_skipped(self):
        a = make_adapter(bot_username="neuralcleavebot")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_webhook_params(username="neuralcleavebot")
        req = fake_form_request(params)
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_other_username_not_skipped(self):
        a = make_adapter(bot_username="neuralcleavebot")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_webhook_params(username="alice")
        req = fake_form_request(params)
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert len(msgs) == 1

    @pytest.mark.asyncio
    async def test_dispatches_inbound_message(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_webhook_params(text="Hello!"))
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello!"

    @pytest.mark.asyncio
    async def test_message_channel(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_webhook_params())
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].channel == "synology_chat"

    @pytest.mark.asyncio
    async def test_sender_id_from_user_id(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_webhook_params(user_id="99"))
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "99"

    @pytest.mark.asyncio
    async def test_sender_name_from_username(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_webhook_params(username="bob"))
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].sender_name == "bob"

    @pytest.mark.asyncio
    async def test_thread_id_includes_channel_id(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_webhook_params(channel_id="15"))
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "channel:15"

    @pytest.mark.asyncio
    async def test_thread_id_uses_user_id_when_no_channel(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_webhook_params(channel_id="")
        req = fake_form_request(params)
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "user:42"

    @pytest.mark.asyncio
    async def test_timestamp_parsed(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_webhook_params(timestamp="1700000000"))
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].timestamp == 1700000000.0

    @pytest.mark.asyncio
    async def test_raw_contains_all_fields(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_webhook_params()
        req = fake_form_request(params)
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].raw == params

    @pytest.mark.asyncio
    async def test_bad_form_data_returns_400(self):
        a = make_adapter()
        req = fake_bad_post_request()
        resp = await a._handle_webhook(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_bad_timestamp_falls_back_gracefully(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_webhook_params(timestamp="not-a-number")
        req = fake_form_request(params)
        resp = await a._handle_webhook(req)
        assert resp.status == 200
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].timestamp > 0


# ===========================================================================
# 6. _handle_health()
# ===========================================================================


class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        a = make_adapter()
        resp = await a._handle_health(MagicMock())
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_body_contains_synology(self):
        a = make_adapter()
        resp = await a._handle_health(MagicMock())
        assert b"Synology" in resp.body or b"OK" in resp.body


# ===========================================================================
# 7. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        assert await make_adapter().send("", "hi") is None

    @pytest.mark.asyncio
    async def test_no_incoming_token_returns_none(self):
        a = make_adapter(incoming_token="")
        assert await a.send("user:1", "hi") is None

    @pytest.mark.asyncio
    async def test_no_synology_url_returns_none(self):
        a = make_adapter(synology_url="")
        assert await a.send("user:1", "hi") is None

    @pytest.mark.asyncio
    async def test_user_target_success_returns_target(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            result = await a.send("user:42", "hello")
        assert result == "user:42"

    @pytest.mark.asyncio
    async def test_channel_target_success_returns_target(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            result = await a.send("channel:7", "hello")
        assert result == "channel:7"

    @pytest.mark.asyncio
    async def test_bare_int_target_success_returns_target(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            result = await a.send("99", "hello")
        assert result == "99"

    @pytest.mark.asyncio
    async def test_api_success_false_returns_none(self):
        a = make_adapter()
        resp = fake_response(200, {"success": False, "error": {"code": 403}})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            result = await a.send("user:1", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        a = make_adapter()
        resp = fake_response(500, {})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            result = await a.send("user:1", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a.send("user:1", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_target_returns_none(self):
        a = make_adapter()
        result = await a.send("notanumber", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_posts_to_correct_url(self):
        a = make_adapter(synology_url="https://nas.example.com:5001")
        resp = fake_response(200, {"success": True})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("user:1", "hi")
        url = client.post.call_args[0][0]
        assert "nas.example.com:5001" in url
        assert _SYNO_API_PATH in url

    @pytest.mark.asyncio
    async def test_posts_correct_api_fields(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("user:1", "hi")
        data = client.post.call_args[1]["data"]
        assert data["api"] == _SYNO_API
        assert data["method"] == _SYNO_METHOD
        assert data["version"] == _SYNO_VERSION
        assert data["token"] == "in_token"

    @pytest.mark.asyncio
    async def test_payload_field_is_json_string(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("user:42", "test message")
        data = client.post.call_args[1]["data"]
        payload = json.loads(data["payload"])
        assert payload["text"] == "test message"
        assert payload["user_ids"] == [42]

    @pytest.mark.asyncio
    async def test_channel_payload_has_channel_id(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("channel:5", "hello channel")
        data = client.post.call_args[1]["data"]
        payload = json.loads(data["payload"])
        assert payload["channel_id"] == 5
        assert "user_ids" not in payload

    @pytest.mark.asyncio
    async def test_timeout_is_set(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.send("user:1", "hi")
        assert client.post.call_args[1]["timeout"] == 15.0


# ===========================================================================
# 8. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_no_incoming_token_returns_false(self):
        assert await make_adapter(incoming_token="").ping() is False

    @pytest.mark.asyncio
    async def test_no_synology_url_returns_false(self):
        assert await make_adapter(synology_url="").ping() is False

    @pytest.mark.asyncio
    async def test_200_returns_true(self):
        a = make_adapter()
        resp = fake_response(200, {"success": True})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            assert await a.ping() is True

    @pytest.mark.asyncio
    async def test_400_returns_true(self):
        a = make_adapter()
        resp = MagicMock()
        resp.status_code = 400
        resp.raise_for_status = MagicMock()
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            assert await a.ping() is True

    @pytest.mark.asyncio
    async def test_500_returns_false(self):
        a = make_adapter()
        resp = MagicMock()
        resp.status_code = 500
        resp.raise_for_status = MagicMock()
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_uses_correct_url(self):
        a = make_adapter(synology_url="https://nas.example.com:5001")
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        url = client.get.call_args[0][0]
        assert "nas.example.com:5001" in url

    @pytest.mark.asyncio
    async def test_timeout_5s(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        assert client.get.call_args[1]["timeout"] == 5.0

    @pytest.mark.asyncio
    async def test_passes_token_in_params(self):
        a = make_adapter(incoming_token="my_tok")
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        params = client.get.call_args[1]["params"]
        assert params["token"] == "my_tok"


# ===========================================================================
# 9. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_incoming_token(self):
        assert "incoming_token" in make_adapter().get_config_schema()["required"]

    def test_required_has_synology_url(self):
        assert "synology_url" in make_adapter().get_config_schema()["required"]

    def test_properties_has_all_keys(self):
        props = make_adapter().get_config_schema()["properties"]
        for key in (
            "token",
            "incoming_token",
            "synology_url",
            "host",
            "port",
            "webhook_path",
            "bot_username",
        ):
            assert key in props, f"Missing property: {key}"

    def test_port_default(self):
        assert make_adapter().get_config_schema()["properties"]["port"]["default"] == 8089

    def test_webhook_path_default(self):
        props = make_adapter().get_config_schema()["properties"]
        assert props["webhook_path"]["default"] == "/webhook/synology_chat"


# ===========================================================================
# 10. Constants
# ===========================================================================


class TestConstants:
    def test_syno_api(self):
        assert _SYNO_API == "SYNO.Chat.External"

    def test_syno_method(self):
        assert _SYNO_METHOD == "incoming"

    def test_syno_version(self):
        assert _SYNO_VERSION == "2"

    def test_syno_api_path(self):
        assert _SYNO_API_PATH == "/webapi/entry.cgi"


# ===========================================================================
# 11. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "synology_chat" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_full_receive_and_reply_flow(self):
        """Receive a webhook, capture the message, then send a reply."""
        a = make_adapter()
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)
            resp = fake_response(200, {"success": True})
            with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
                await a.send(msg.thread_id, "Got it!")

        a.on_message(handler)
        req = fake_form_request(make_webhook_params(text="ping", channel_id="3"))
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].text == "ping"
        assert msgs[0].thread_id == "channel:3"

    @pytest.mark.asyncio
    async def test_multiple_webhooks_dispatched_independently(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        for i in range(5):
            req = fake_form_request(
                make_webhook_params(text=f"msg {i}", user_id=str(i + 1))
            )
            await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert len(msgs) == 5
        texts = [m.text for m in msgs]
        for i in range(5):
            assert f"msg {i}" in texts

    @pytest.mark.asyncio
    async def test_unicode_text_dispatched(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_webhook_params(text="こんにちは 🌸"))
        await a._handle_webhook(req)
        import asyncio
        await asyncio.sleep(0)
        assert msgs[0].text == "こんにちは 🌸"

    @pytest.mark.asyncio
    async def test_no_handler_does_not_raise_on_webhook(self):
        a = make_adapter()
        req = fake_form_request(make_webhook_params())
        resp = await a._handle_webhook(req)
        assert resp.status == 200
