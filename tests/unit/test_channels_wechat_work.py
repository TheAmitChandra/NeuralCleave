"""Unit tests for cortexflow_ai.channels.wechat_work — WeChatWorkAdapter.

Covers:
  - Constructor / defaults / config parsing
  - is_connected lifecycle
  - connect() / disconnect()
  - _verify_signature() — valid, invalid, no token dev mode, sorting
  - _get_access_token() — cache hit, refresh, expiry buffer, missing creds, error
  - _build_send_payload() — touser/toparty/totag/@all/bare string
  - _handle_verify() — GET verification challenge, sig check, echostr return
  - _handle_message() — POST: sig check, XML parse, all message types,
      event types (ignored), echo guard, empty content, dispatch
  - send() — success, no target, no token, API error, network error,
      all target formats
  - ping() — token ok, token empty
  - get_config_schema() — shape and required fields
  - Constants
  - Edge / integration cases
"""

from __future__ import annotations

import asyncio
import hashlib
import xml.etree.ElementTree as ET
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.channels.wechat_work import (
    _SEND_URL,
    _TOKEN_URL,
    WeChatWorkAdapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides: Any) -> WeChatWorkAdapter:
    cfg: dict[str, Any] = {
        "corpid": "ww1234567890",
        "corpsecret": "mysecret",
        "agentid": 1000002,
        "token": "mytoken",
        **overrides,
    }
    return WeChatWorkAdapter(cfg)


def _sha1_sig(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()


def _make_xml(
    msg_type: str = "text",
    from_user: str = "alice",
    to_user: str = "oa123",
    content: str = "Hello!",
    create_time: int = 1700000000,
    msg_id: str = "12345678901234567",
    agent_id: str = "1000002",
    extra_tags: str = "",
) -> bytes:
    if msg_type == "text":
        body_tag = f"<Content><![CDATA[{content}]]></Content>"
    elif msg_type == "image":
        body_tag = "<PicUrl><![CDATA[https://example.com/img.jpg]]></PicUrl><MediaId><![CDATA[media001]]></MediaId>"
    elif msg_type == "voice":
        body_tag = "<MediaId><![CDATA[media002]]></MediaId><Format><![CDATA[amr]]></Format>"
    elif msg_type == "video":
        body_tag = "<MediaId><![CDATA[media003]]></MediaId><ThumbMediaId><![CDATA[thumb001]]></ThumbMediaId>"
    elif msg_type == "location":
        body_tag = (
            "<Location_X>23.137466</Location_X>"
            "<Location_Y>113.352425</Location_Y>"
            "<Scale>20</Scale>"
            "<Label><![CDATA[Guangzhou]]></Label>"
        )
    elif msg_type == "link":
        body_tag = (
            "<Title><![CDATA[Test Link]]></Title>"
            "<Description><![CDATA[A link]]></Description>"
            "<Url><![CDATA[https://example.com]]></Url>"
            "<PicUrl><![CDATA[https://example.com/pic.jpg]]></PicUrl>"
        )
    elif msg_type == "file":
        body_tag = "<MediaId><![CDATA[media004]]></MediaId>"
    elif msg_type == "event":
        body_tag = f"<Event><![CDATA[{content}]]></Event>"
    else:
        body_tag = ""

    return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[{msg_type}]]></MsgType>
{body_tag}
<MsgId>{msg_id}</MsgId>
<AgentID>{agent_id}</AgentID>
{extra_tags}
</xml>""".encode()


def _mock_request(method: str, body: bytes, query: dict) -> MagicMock:
    req = MagicMock()
    req.method = method
    req.read = AsyncMock(return_value=body)
    req.query = query
    return req


async def _post_xml(adapter: WeChatWorkAdapter, body: bytes, token: str = "mytoken") -> Any:
    ts = "1700000000"
    nonce = "abc123"
    sig = _sha1_sig(token, ts, nonce)
    req = _mock_request("POST", body, {"msg_signature": sig, "timestamp": ts, "nonce": nonce})
    return await adapter._handle_message(req)


def fake_token_response(token: str = "newtoken", expires: int = 7200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"access_token": token, "expires_in": expires, "errcode": 0})
    return resp


def fake_send_response(errcode: int = 0, errmsg: str = "ok") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"errcode": errcode, "errmsg": errmsg, "msgid": "msg001"})
    return resp


def fake_http_client(**method_responses: MagicMock) -> MagicMock:
    client = AsyncMock()
    for method, resp in method_responses.items():
        setattr(client, method, AsyncMock(return_value=resp))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ===========================================================================
# 1. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_corpid_empty(self):
        assert WeChatWorkAdapter({})._corpid == ""

    def test_default_corpsecret_empty(self):
        assert WeChatWorkAdapter({})._corpsecret == ""

    def test_default_agentid_zero(self):
        assert WeChatWorkAdapter({})._agentid == 0

    def test_default_token_empty(self):
        assert WeChatWorkAdapter({})._token == ""

    def test_default_bot_userid_empty(self):
        assert WeChatWorkAdapter({})._bot_userid == ""

    def test_default_host(self):
        assert make_adapter()._host == "0.0.0.0"

    def test_default_port(self):
        assert make_adapter()._port == 8092

    def test_default_webhook_path(self):
        assert make_adapter()._webhook_path == "/webhook/wechat_work"

    def test_access_token_empty_initially(self):
        assert make_adapter()._access_token == ""

    def test_token_expires_at_zero(self):
        assert make_adapter()._token_expires_at == 0.0

    def test_runner_none_initially(self):
        assert make_adapter()._runner is None

    def test_agentid_coerced_from_string(self):
        assert make_adapter(agentid="1000003")._agentid == 1000003

    def test_port_coerced_from_string(self):
        assert make_adapter(port="9000")._port == 9000

    def test_custom_host(self):
        assert make_adapter(host="127.0.0.1")._host == "127.0.0.1"

    def test_custom_webhook_path(self):
        assert make_adapter(webhook_path="/wx/in")._webhook_path == "/wx/in"

    def test_custom_bot_userid(self):
        assert make_adapter(bot_userid="cortex_bot")._bot_userid == "cortex_bot"

    def test_channel_id_class(self):
        assert WeChatWorkAdapter.channel_id == "wechat_work"

    def test_channel_id_instance(self):
        assert make_adapter().channel_id == "wechat_work"


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
    async def test_connect_starts_site(self):
        a = make_adapter()
        with patch("aiohttp.web.AppRunner") as mr, patch("aiohttp.web.TCPSite") as ms:
            mock_runner = AsyncMock()
            mr.return_value = mock_runner
            mock_site = AsyncMock()
            ms.return_value = mock_site
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
        a = make_adapter(token="tok")
        sig = _sha1_sig("tok", "ts1", "nonce1")
        assert a._verify_signature("ts1", "nonce1", sig) is True

    def test_invalid_signature(self):
        a = make_adapter(token="tok")
        assert a._verify_signature("ts1", "nonce1", "badsig") is False

    def test_empty_sig_with_token_set(self):
        a = make_adapter(token="tok")
        assert a._verify_signature("ts", "nonce", "") is False

    def test_no_token_dev_mode_accepts_empty_sig(self):
        a = make_adapter(token="")
        assert a._verify_signature("ts", "nonce", "") is True

    def test_no_token_dev_mode_accepts_any_sig(self):
        a = make_adapter(token="")
        assert a._verify_signature("ts", "nonce", "anything") is True

    def test_signature_is_sorted(self):
        a = make_adapter(token="zzz")
        sig_forward = hashlib.sha1("".join(["zzz", "aaa", "bbb"]).encode()).hexdigest()
        sig_sorted = hashlib.sha1("".join(sorted(["zzz", "aaa", "bbb"])).encode()).hexdigest()
        assert a._verify_signature("aaa", "bbb", sig_sorted) is True
        assert a._verify_signature("aaa", "bbb", sig_forward) is False

    def test_different_token_fails(self):
        a = make_adapter(token="correct")
        sig = _sha1_sig("wrong", "ts", "nonce")
        assert a._verify_signature("ts", "nonce", sig) is False

    def test_sha1_not_sha256(self):
        import hmac as _hmac
        a = make_adapter(token="tok")
        sha256_sig = _hmac.new(b"tok", b"tsnonceok", __import__("hashlib").sha256).hexdigest()
        sha1_sig = _sha1_sig("tok", "ts", "nonce")
        assert a._verify_signature("ts", "nonce", sha1_sig) is True
        assert a._verify_signature("ts", "nonce", sha256_sig) is False


# ===========================================================================
# 5. _get_access_token()
# ===========================================================================


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_returns_cached_token(self):
        import time
        a = make_adapter()
        a._access_token = "cached"
        a._token_expires_at = time.time() + 3600
        assert await a._get_access_token() == "cached"

    @pytest.mark.asyncio
    async def test_refreshes_expired_token(self):
        import time
        a = make_adapter()
        a._token_expires_at = time.time() - 1
        resp = fake_token_response("fresh")
        with patch("httpx.AsyncClient", return_value=fake_http_client(get=resp)):
            assert await a._get_access_token() == "fresh"

    @pytest.mark.asyncio
    async def test_refreshes_within_60s_buffer(self):
        import time
        a = make_adapter()
        a._access_token = "expiring"
        a._token_expires_at = time.time() + 30
        resp = fake_token_response("fresh")
        with patch("httpx.AsyncClient", return_value=fake_http_client(get=resp)):
            assert await a._get_access_token() == "fresh"

    @pytest.mark.asyncio
    async def test_returns_empty_no_corpid(self):
        assert await make_adapter(corpid="")._get_access_token() == ""

    @pytest.mark.asyncio
    async def test_returns_empty_no_corpsecret(self):
        assert await make_adapter(corpsecret="")._get_access_token() == ""

    @pytest.mark.asyncio
    async def test_stores_new_token(self):
        a = make_adapter()
        resp = fake_token_response("stored")
        with patch("httpx.AsyncClient", return_value=fake_http_client(get=resp)):
            await a._get_access_token()
        assert a._access_token == "stored"

    @pytest.mark.asyncio
    async def test_stores_expiry(self):
        import time
        a = make_adapter()
        before = time.time()
        resp = fake_token_response("tok", 7200)
        with patch("httpx.AsyncClient", return_value=fake_http_client(get=resp)):
            await a._get_access_token()
        assert a._token_expires_at >= before + 7200 - 1

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
        resp.json = MagicMock(return_value={"errcode": 40013, "errmsg": "invalid corpid"})
        with patch("httpx.AsyncClient", return_value=fake_http_client(get=resp)):
            assert await a._get_access_token() == ""

    @pytest.mark.asyncio
    async def test_posts_to_token_url(self):
        a = make_adapter()
        resp = fake_token_response()
        client = fake_http_client(get=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        url = client.get.call_args[0][0]
        assert url == _TOKEN_URL

    @pytest.mark.asyncio
    async def test_sends_corpid_and_corpsecret(self):
        a = make_adapter(corpid="ww123", corpsecret="sec456")
        resp = fake_token_response()
        client = fake_http_client(get=resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._get_access_token()
        params = client.get.call_args[1]["params"]
        assert params["corpid"] == "ww123"
        assert params["corpsecret"] == "sec456"


# ===========================================================================
# 6. _build_send_payload()
# ===========================================================================


class TestBuildSendPayload:
    def test_bare_string_is_touser(self):
        p = make_adapter()._build_send_payload("alice", "hi")
        assert p["touser"] == "alice"

    def test_touser_prefix(self):
        p = make_adapter()._build_send_payload("touser:alice", "hi")
        assert p["touser"] == "alice"

    def test_user_prefix(self):
        p = make_adapter()._build_send_payload("user:alice", "hi")
        assert p["touser"] == "alice"

    def test_toparty_prefix(self):
        p = make_adapter()._build_send_payload("toparty:dept1", "hi")
        assert p["toparty"] == "dept1"

    def test_party_prefix(self):
        p = make_adapter()._build_send_payload("party:dept2", "hi")
        assert p["toparty"] == "dept2"

    def test_totag_prefix(self):
        p = make_adapter()._build_send_payload("totag:tag1", "hi")
        assert p["totag"] == "tag1"

    def test_tag_prefix(self):
        p = make_adapter()._build_send_payload("tag:tag2", "hi")
        assert p["totag"] == "tag2"

    def test_at_all(self):
        p = make_adapter()._build_send_payload("@all", "broadcast")
        assert p["touser"] == "@all"

    def test_msg_type_is_text(self):
        p = make_adapter()._build_send_payload("alice", "hi")
        assert p["msgtype"] == "text"

    def test_text_content_set(self):
        p = make_adapter()._build_send_payload("alice", "hello world")
        assert p["text"]["content"] == "hello world"

    def test_agentid_set(self):
        p = make_adapter(agentid=9999)._build_send_payload("alice", "hi")
        assert p["agentid"] == 9999

    def test_no_extra_target_keys_for_touser(self):
        p = make_adapter()._build_send_payload("alice", "hi")
        assert "toparty" not in p
        assert "totag" not in p


# ===========================================================================
# 7. _handle_verify() — GET endpoint
# ===========================================================================


class TestHandleVerify:
    @pytest.mark.asyncio
    async def test_valid_signature_returns_echostr(self):
        a = make_adapter(token="tok")
        ts, nonce = "1700000000", "abc"
        sig = _sha1_sig("tok", ts, nonce)
        req = MagicMock()
        req.query = {"msg_signature": sig, "timestamp": ts, "nonce": nonce, "echostr": "ECHO123"}
        resp = await a._handle_verify(req)
        assert resp.status == 200
        assert resp.text == "ECHO123"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self):
        a = make_adapter(token="tok")
        req = MagicMock()
        req.query = {"msg_signature": "badsig", "timestamp": "ts", "nonce": "nonce", "echostr": "ECHO"}
        resp = await a._handle_verify(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_no_token_dev_mode_returns_echostr(self):
        a = make_adapter(token="")
        req = MagicMock()
        req.query = {"msg_signature": "", "timestamp": "ts", "nonce": "nonce", "echostr": "DEVECHO"}
        resp = await a._handle_verify(req)
        assert resp.status == 200
        assert resp.text == "DEVECHO"

    @pytest.mark.asyncio
    async def test_uses_signature_query_param_fallback(self):
        a = make_adapter(token="tok")
        ts, nonce = "1700000000", "abc"
        sig = _sha1_sig("tok", ts, nonce)
        req = MagicMock()
        req.query = {"signature": sig, "timestamp": ts, "nonce": nonce, "echostr": "OK"}
        resp = await a._handle_verify(req)
        assert resp.status == 200


# ===========================================================================
# 8. _handle_message() — POST endpoint
# ===========================================================================


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_text_message_dispatched(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="text", content="Hello WeChat!")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello WeChat!"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self):
        a = make_adapter(token="tok")
        req = _mock_request("POST", _make_xml(), {"msg_signature": "badsig", "timestamp": "ts", "nonce": "nonce"})
        resp = await a._handle_message(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_malformed_xml_returns_400(self):
        a = make_adapter(token="")
        req = _mock_request("POST", b"NOT XML <<<", {"msg_signature": "", "timestamp": "ts", "nonce": "nonce"})
        resp = await a._handle_message(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_event_type_not_dispatched(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="event", content="subscribe")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_image_message_dispatched_with_placeholder(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="image")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert "[image]" in msgs[0].text

    @pytest.mark.asyncio
    async def test_voice_message_dispatched_with_placeholder(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="voice")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert "[voice]" in msgs[0].text

    @pytest.mark.asyncio
    async def test_video_message_dispatched_with_placeholder(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="video")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert "[video]" in msgs[0].text

    @pytest.mark.asyncio
    async def test_file_message_dispatched_with_placeholder(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="file")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert "[file]" in msgs[0].text

    @pytest.mark.asyncio
    async def test_location_message_includes_label_and_coords(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="location")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert "Guangzhou" in msgs[0].text
        assert "23.137466" in msgs[0].text

    @pytest.mark.asyncio
    async def test_link_message_includes_title_and_url(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="link")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert "Test Link" in msgs[0].text
        assert "https://example.com" in msgs[0].text

    @pytest.mark.asyncio
    async def test_echo_guard_drops_bot_userid(self):
        a = make_adapter(token="mytoken", bot_userid="alice")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="text", from_user="alice", content="echo!")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_different_user_not_dropped(self):
        a = make_adapter(token="mytoken", bot_userid="bot_user")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="text", from_user="alice", content="hello")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert len(msgs) == 1

    @pytest.mark.asyncio
    async def test_sender_id_from_fromuser(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(from_user="user_xyz")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs[0].sender_id == "user_xyz"

    @pytest.mark.asyncio
    async def test_thread_id_from_agentid(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(agent_id="9001")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == "9001"

    @pytest.mark.asyncio
    async def test_timestamp_from_create_time(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(create_time=1700000001)
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs[0].timestamp == 1700000001.0

    @pytest.mark.asyncio
    async def test_channel_id_in_message(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml()
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs[0].channel == "wechat_work"

    @pytest.mark.asyncio
    async def test_raw_contains_msg_type(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="text", msg_id="raw-check-999")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs[0].raw["msg_type"] == "text"
        assert msgs[0].raw["msg_id"] == "raw-check-999"

    @pytest.mark.asyncio
    async def test_empty_text_not_dispatched(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="text", content="")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_unknown_msg_type_not_dispatched(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="shortvideo")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_returns_success_string(self):
        a = make_adapter(token="mytoken")
        xml = _make_xml()
        resp = await _post_xml(a, xml)
        assert resp.text == "success"

    @pytest.mark.asyncio
    async def test_no_token_dev_mode_accepts_empty_sig(self):
        a = make_adapter(token="")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = _mock_request("POST", _make_xml(content="devmode"), {"msg_signature": "", "timestamp": "ts", "nonce": "nonce"})
        await a._handle_message(req)
        await asyncio.sleep(0)
        assert msgs[0].text == "devmode"


# ===========================================================================
# 9. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        assert await make_adapter().send("", "hi") is None

    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="")):
            assert await a.send("alice", "hi") is None

    @pytest.mark.asyncio
    async def test_success_returns_target(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(0)
            with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
                assert await a.send("alice", "Hello!") == "alice"

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response(60011)
            with patch("httpx.AsyncClient", return_value=fake_http_client(post=resp)):
                assert await a.send("alice", "Hello!") is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            client = AsyncMock()
            client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
            client.__aexit__ = AsyncMock(return_value=False)
            with patch("httpx.AsyncClient", return_value=client):
                assert await a.send("alice", "Hi") is None

    @pytest.mark.asyncio
    async def test_posts_to_send_url(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("alice", "Hi")
        assert client.post.call_args[0][0] == _SEND_URL

    @pytest.mark.asyncio
    async def test_access_token_in_query_params(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="mytoken")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("alice", "Hi")
        assert client.post.call_args[1]["params"]["access_token"] == "mytoken"

    @pytest.mark.asyncio
    async def test_send_toparty_target(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("toparty:dept1", "hi")
        assert result == "toparty:dept1"
        payload = client.post.call_args[1]["json"]
        assert payload["toparty"] == "dept1"

    @pytest.mark.asyncio
    async def test_send_totag_target(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("totag:tag1", "hi")
        assert result == "totag:tag1"

    @pytest.mark.asyncio
    async def test_send_at_all(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("@all", "broadcast")
        assert result == "@all"

    @pytest.mark.asyncio
    async def test_unicode_text(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                result = await a.send("alice", "你好 🌸")
        assert result == "alice"


# ===========================================================================
# 10. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_valid_token_returns_true(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            assert await a.ping() is True

    @pytest.mark.asyncio
    async def test_empty_token_returns_false(self):
        a = make_adapter()
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="")):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_no_corpid_returns_false(self):
        assert await make_adapter(corpid="").ping() is False

    @pytest.mark.asyncio
    async def test_no_corpsecret_returns_false(self):
        assert await make_adapter(corpsecret="").ping() is False


# ===========================================================================
# 11. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_corpid(self):
        assert "corpid" in make_adapter().get_config_schema()["required"]

    def test_required_has_corpsecret(self):
        assert "corpsecret" in make_adapter().get_config_schema()["required"]

    def test_required_has_agentid(self):
        assert "agentid" in make_adapter().get_config_schema()["required"]

    def test_properties_present(self):
        props = make_adapter().get_config_schema()["properties"]
        for k in ("corpid", "corpsecret", "agentid", "token", "bot_userid",
                  "host", "port", "webhook_path"):
            assert k in props

    def test_port_default(self):
        assert make_adapter().get_config_schema()["properties"]["port"]["default"] == 8092

    def test_host_default(self):
        assert make_adapter().get_config_schema()["properties"]["host"]["default"] == "0.0.0.0"

    def test_webhook_path_default(self):
        schema = make_adapter().get_config_schema()
        assert schema["properties"]["webhook_path"]["default"] == "/webhook/wechat_work"


# ===========================================================================
# 12. Constants
# ===========================================================================


class TestConstants:
    def test_token_url(self):
        assert _TOKEN_URL == "https://qyapi.weixin.qq.com/cgi-bin/gettoken"

    def test_send_url(self):
        assert _SEND_URL == "https://qyapi.weixin.qq.com/cgi-bin/message/send"


# ===========================================================================
# 13. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "wechat_work" in repr(make_adapter())

    def test_xml_text_helper_missing_tag(self):
        from cortexflow_ai.channels.wechat_work import _xml_text
        root = ET.fromstring("<xml><Foo>bar</Foo></xml>")
        assert _xml_text(root, "Missing", "default") == "default"

    def test_xml_text_helper_present_tag(self):
        from cortexflow_ai.channels.wechat_work import _xml_text
        root = ET.fromstring("<xml><Foo>bar</Foo></xml>")
        assert _xml_text(root, "Foo") == "bar"

    def test_xml_text_helper_cdata(self):
        from cortexflow_ai.channels.wechat_work import _xml_text
        root = ET.fromstring("<xml><Content><![CDATA[hello world]]></Content></xml>")
        assert _xml_text(root, "Content") == "hello world"

    @pytest.mark.asyncio
    async def test_multiple_messages_sequential(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        for i in range(3):
            xml = _make_xml(content=f"msg{i}", msg_id=str(i))
            await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert len(msgs) == 3
        texts = {m.text for m in msgs}
        assert texts == {"msg0", "msg1", "msg2"}

    @pytest.mark.asyncio
    async def test_subscribe_event_not_dispatched(self):
        a = make_adapter(token="mytoken")
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        xml = _make_xml(msg_type="event", content="subscribe")
        await _post_xml(a, xml)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_send_uses_agentid_in_payload(self):
        a = make_adapter(agentid=555)
        with patch.object(a, "_get_access_token", new=AsyncMock(return_value="tok")):
            resp = fake_send_response()
            client = fake_http_client(post=resp)
            with patch("httpx.AsyncClient", return_value=client):
                await a.send("alice", "hi")
        payload = client.post.call_args[1]["json"]
        assert payload["agentid"] == 555
