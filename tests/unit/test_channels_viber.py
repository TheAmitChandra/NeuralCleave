"""Unit tests for cortexflow.channels.viber — ViberAdapter."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

from cortexflow_ai.channels.viber import ViberAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides) -> ViberAdapter:
    cfg = {
        "auth_token": "viber-token-abc",
        "webhook_url": "https://example.com/webhooks/viber",
        "bot_name": "TestBot",
        **overrides,
    }
    return ViberAdapter(cfg)


def _sign(auth_token: str, body: bytes) -> str:
    return hmac.new(auth_token.encode(), body, hashlib.sha256).hexdigest()


def _fake_session(post_data=None, get_data=None, raise_on_post=False, raise_on_get=False):
    post_data = post_data or {"status": 0, "message_token": 999}
    get_data = get_data or {"status": 0, "name": "TestBot"}

    class _Resp:
        def __init__(self, data, ok=True):
            self._data = data
            self._ok = ok
            self.status = 200 if ok else 500

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            if not self._ok:
                raise Exception("HTTP error")

        async def json(self):
            return self._data

    class _Session:
        def post(self, *_, **__):
            if raise_on_post:
                raise RuntimeError("post failed")
            return _Resp(post_data)

        def get(self, *_, **__):
            if raise_on_get:
                raise RuntimeError("get failed")
            return _Resp(get_data)

        async def close(self):
            pass

    return _Session()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "viber"


def test_defaults():
    a = ViberAdapter({})
    assert a._auth_token == ""
    assert a._webhook_url == ""
    assert a._bot_name == "CortexFlowBot"
    assert a._verify_sig is True
    assert a._connected is False


def test_custom_bot_name():
    a = make_adapter(bot_name="MyViberBot")
    assert a._bot_name == "MyViberBot"


def test_custom_bot_avatar():
    a = make_adapter(bot_avatar="https://example.com/avatar.png")
    assert a._bot_avatar == "https://example.com/avatar.png"


def test_verify_signature_can_be_disabled():
    a = make_adapter(verify_signature=False)
    assert a._verify_sig is False


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("VIBER_TOKEN_TEST", "resolved-token")
    a = make_adapter(auth_token="ENV:VIBER_TOKEN_TEST")
    assert a._auth_token == "resolved-token"


def test_resolve_env_missing(monkeypatch):
    monkeypatch.delenv("VIBER_MISSING", raising=False)
    a = make_adapter(auth_token="ENV:VIBER_MISSING")
    assert a._auth_token == ""


def test_resolve_plain_string_unchanged():
    a = make_adapter(auth_token="plain")
    assert a._auth_token == "plain"


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------


def test_config_schema_required():
    schema = make_adapter().get_config_schema()
    assert "auth_token" in schema["required"]


def test_config_schema_optional_fields():
    schema = make_adapter().get_config_schema()
    props = schema["properties"]
    assert "webhook_url" in props
    assert "bot_name" in props
    assert "verify_signature" in props


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_if_aiohttp_not_installed():
    adapter = make_adapter()
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aiohttp":
            raise ImportError("no aiohttp")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="aiohttp"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_raises_missing_auth_token():
    adapter = ViberAdapter({"webhook_url": "https://example.com/webhooks/viber"})
    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession.return_value = _fake_session()
    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
        with pytest.raises(RuntimeError, match="auth_token"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_sets_connected_true():
    adapter = make_adapter()
    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession.return_value = _fake_session(
        post_data={"status": 0, "status_message": "ok"}
    )
    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
        await adapter.connect()
    assert adapter._connected is True
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_connect_no_webhook_url_skips_set_webhook():
    adapter = make_adapter(webhook_url="")
    mock_aiohttp = MagicMock()
    session = _fake_session()
    calls = []
    original_post = session.post

    def tracked_post(*args, **kwargs):
        calls.append(args)
        return original_post(*args, **kwargs)

    session.post = tracked_post  # type: ignore[method-assign]
    mock_aiohttp.ClientSession.return_value = session

    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
        await adapter.connect()

    assert calls == []
    await adapter.disconnect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_without_connect_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()
    assert adapter._connected is False
    assert adapter._session is None


@pytest.mark.asyncio
async def test_disconnect_sets_connected_false():
    adapter = make_adapter()
    adapter._connected = True
    adapter._session = _fake_session()
    await adapter.disconnect()
    assert adapter._connected is False


@pytest.mark.asyncio
async def test_disconnect_closes_session():
    adapter = make_adapter()
    closed = []
    session = _fake_session()

    async def _close():
        closed.append(True)

    session.close = _close  # type: ignore[method-assign]
    adapter._connected = True
    adapter._session = session
    await adapter.disconnect()
    assert closed


# ---------------------------------------------------------------------------
# is_connected (via _connected flag)
# ---------------------------------------------------------------------------


def test_is_connected_true_when_connected():
    adapter = make_adapter()
    adapter._connected = True
    assert adapter.is_connected is True


def test_is_connected_false_when_not_connected():
    adapter = make_adapter()
    assert adapter.is_connected is False


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_session_returns_none():
    adapter = make_adapter()
    result = await adapter.send("user123", "hi")
    assert result is None


@pytest.mark.asyncio
async def test_send_success_returns_token():
    adapter = make_adapter()
    adapter._session = _fake_session(post_data={"status": 0, "message_token": 42})
    result = await adapter.send("user123", "hello")
    assert result == "42"


@pytest.mark.asyncio
async def test_send_api_error_status_returns_none():
    adapter = make_adapter()
    adapter._session = _fake_session(post_data={"status": 6, "status_message": "failed"})
    result = await adapter.send("user123", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_truncates_to_7000_chars():
    adapter = make_adapter()
    sent_payloads = []

    async def capturing_post(path, payload):
        sent_payloads.append(payload)
        return {"status": 0, "message_token": 1}

    adapter._api_post = capturing_post  # type: ignore[method-assign]
    adapter._session = _fake_session()
    await adapter.send("user123", "x" * 8000)
    assert len(sent_payloads[0]["text"]) == 7000


@pytest.mark.asyncio
async def test_send_includes_avatar_when_set():
    adapter = make_adapter(bot_avatar="https://example.com/avatar.png")
    sent_payloads = []

    async def capturing_post(path, payload):
        sent_payloads.append(payload)
        return {"status": 0, "message_token": 2}

    adapter._api_post = capturing_post  # type: ignore[method-assign]
    adapter._session = _fake_session()
    await adapter.send("user123", "hello")
    assert sent_payloads[0]["sender"]["avatar"] == "https://example.com/avatar.png"


@pytest.mark.asyncio
async def test_send_no_avatar_when_not_set():
    adapter = make_adapter(bot_avatar="")
    sent_payloads = []

    async def capturing_post(path, payload):
        sent_payloads.append(payload)
        return {"status": 0, "message_token": 3}

    adapter._api_post = capturing_post  # type: ignore[method-assign]
    adapter._session = _fake_session()
    await adapter.send("user123", "hello")
    assert "avatar" not in sent_payloads[0]["sender"]


@pytest.mark.asyncio
async def test_send_exception_returns_none():
    adapter = make_adapter()
    adapter._session = _fake_session(raise_on_post=True)
    result = await adapter.send("user123", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# ping()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_no_session_returns_false():
    adapter = make_adapter()
    assert await adapter.ping() is False


@pytest.mark.asyncio
async def test_ping_success_returns_true():
    adapter = make_adapter()
    adapter._session = _fake_session(get_data={"status": 0, "name": "TestBot"})
    assert await adapter.ping() is True


@pytest.mark.asyncio
async def test_ping_non_zero_status_returns_false():
    adapter = make_adapter()
    adapter._session = _fake_session(get_data={"status": 1, "status_message": "error"})
    assert await adapter.ping() is False


@pytest.mark.asyncio
async def test_ping_exception_returns_false():
    adapter = make_adapter()
    adapter._session = _fake_session(raise_on_get=True)
    assert await adapter.ping() is False


# ---------------------------------------------------------------------------
# _check_signature()
# ---------------------------------------------------------------------------


def test_check_signature_valid():
    adapter = make_adapter(auth_token="my-token")
    body = b'{"event":"message"}'
    sig = _sign("my-token", body)
    assert adapter._check_signature(body, sig) is True


def test_check_signature_invalid():
    adapter = make_adapter(auth_token="my-token")
    body = b'{"event":"message"}'
    assert adapter._check_signature(body, "wrong-sig") is False


def test_check_signature_empty_body():
    adapter = make_adapter(auth_token="my-token")
    body = b""
    sig = _sign("my-token", body)
    assert adapter._check_signature(body, sig) is True


def test_check_signature_tampered_body():
    adapter = make_adapter(auth_token="my-token")
    body = b'{"event":"message"}'
    sig = _sign("my-token", body)
    tampered = b'{"event":"message","injected":true}'
    assert adapter._check_signature(tampered, sig) is False


# ---------------------------------------------------------------------------
# handle_webhook() — signature rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_rejects_bad_signature():
    adapter = make_adapter(verify_signature=True)
    body = json.dumps({"event": "message"}).encode()
    result = await adapter.handle_webhook(body, "bad-sig")
    assert result is False


@pytest.mark.asyncio
async def test_handle_webhook_skips_signature_when_disabled():
    adapter = make_adapter(verify_signature=False)
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    event = {
        "event": "message",
        "sender": {"id": "user1", "name": "Alice"},
        "message": {"type": "text", "text": "hello"},
        "chat_hostname": "chat-123",
    }
    body = json.dumps(event).encode()
    result = await adapter.handle_webhook(body, "any-sig")
    assert result is True
    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_handle_webhook_invalid_json_returns_false():
    adapter = make_adapter(verify_signature=False)
    result = await adapter.handle_webhook(b"not-json", "")
    assert result is False


# ---------------------------------------------------------------------------
# handle_webhook() — event types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_message_event_dispatches():
    adapter = make_adapter(verify_signature=False)
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    event = {
        "event": "message",
        "sender": {"id": "user1", "name": "Alice"},
        "message": {"type": "text", "text": "hi bot"},
    }
    body = json.dumps(event).encode()
    result = await adapter.handle_webhook(body, "")
    assert result is True
    assert len(dispatched) == 1
    assert dispatched[0].text == "hi bot"
    assert dispatched[0].sender_id == "user1"
    assert dispatched[0].sender_name == "Alice"
    assert dispatched[0].channel == "viber"


@pytest.mark.asyncio
async def test_handle_webhook_subscribed_event_returns_true():
    adapter = make_adapter(verify_signature=False)
    event = {"event": "subscribed", "user": {"id": "user1", "name": "Alice"}}
    body = json.dumps(event).encode()
    result = await adapter.handle_webhook(body, "")
    assert result is True


@pytest.mark.asyncio
async def test_handle_webhook_conversation_started_returns_true():
    adapter = make_adapter(verify_signature=False)
    event = {"event": "conversation_started", "user": {"id": "user1", "name": "Bob"}}
    body = json.dumps(event).encode()
    result = await adapter.handle_webhook(body, "")
    assert result is True


@pytest.mark.asyncio
async def test_handle_webhook_unknown_event_returns_false():
    adapter = make_adapter(verify_signature=False)
    event = {"event": "delivered"}
    body = json.dumps(event).encode()
    result = await adapter.handle_webhook(body, "")
    assert result is False


# ---------------------------------------------------------------------------
# _parse_message_event() — message types
# ---------------------------------------------------------------------------


def test_parse_text_message():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "text", "text": "hello"},
    }
    msg = adapter._parse_message_event(event)
    assert msg is not None
    assert msg.text == "hello"
    assert msg.attachments == []


def test_parse_picture_message():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "picture", "media": "https://example.com/pic.jpg"},
    }
    msg = adapter._parse_message_event(event)
    assert msg is not None
    assert msg.text == "[image]"
    assert len(msg.attachments) == 1
    assert msg.attachments[0].type == "image"
    assert msg.attachments[0].url == "https://example.com/pic.jpg"


def test_parse_video_message():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "video", "media": "https://example.com/vid.mp4"},
    }
    msg = adapter._parse_message_event(event)
    assert msg.text == "[video]"
    assert msg.attachments[0].type == "video"


def test_parse_file_message():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "file", "media": "https://example.com/doc.pdf", "file_name": "doc.pdf"},
    }
    msg = adapter._parse_message_event(event)
    assert "[file:" in msg.text
    assert msg.attachments[0].type == "document"
    assert msg.attachments[0].filename == "doc.pdf"


def test_parse_contact_message():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "contact", "contact": {"name": "Bob", "phone_number": "123"}},
    }
    msg = adapter._parse_message_event(event)
    assert "[contact:" in msg.text
    assert "Bob" in msg.text


def test_parse_url_message():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "url", "media": "https://example.com"},
    }
    msg = adapter._parse_message_event(event)
    assert msg.text == "https://example.com"


def test_parse_sticker_message():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "sticker", "sticker_id": 999},
    }
    msg = adapter._parse_message_event(event)
    assert msg.text == "[sticker]"


def test_parse_empty_text_and_sender_returns_none():
    adapter = make_adapter()
    event = {
        "sender": {},
        "message": {"type": "unknown"},
    }
    msg = adapter._parse_message_event(event)
    assert msg is None


def test_parse_message_thread_id_from_chat_hostname():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "text", "text": "hi"},
        "chat_hostname": "chat-abc",
    }
    msg = adapter._parse_message_event(event)
    assert msg.thread_id == "chat-abc"


def test_parse_message_thread_id_fallback_to_sender_id():
    adapter = make_adapter()
    event = {
        "sender": {"id": "user1", "name": "Alice"},
        "message": {"type": "text", "text": "hi"},
    }
    msg = adapter._parse_message_event(event)
    assert msg.thread_id == "user1"


def test_parse_picture_with_caption():
    adapter = make_adapter()
    event = {
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "picture", "text": "my caption", "media": "https://example.com/pic.jpg"},
    }
    msg = adapter._parse_message_event(event)
    assert msg.text == "my caption"


# ---------------------------------------------------------------------------
# handle_webhook() — signature with correct token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_valid_signature_dispatches():
    adapter = make_adapter(auth_token="my-token", verify_signature=True)
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    event = {
        "event": "message",
        "sender": {"id": "u1", "name": "Alice"},
        "message": {"type": "text", "text": "hello"},
    }
    body = json.dumps(event, separators=(",", ":")).encode()
    sig = _sign("my-token", body)

    result = await adapter.handle_webhook(body, sig)
    assert result is True
    assert len(dispatched) == 1
