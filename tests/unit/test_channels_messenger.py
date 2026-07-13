"""Unit tests for cortexflow.channels.messenger — MessengerAdapter."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.channels.messenger import MessengerAdapter


def make_adapter(**overrides) -> MessengerAdapter:
    cfg = {
        "page_access_token": "EAAG-test-token",
        "verify_token": "my-verify-token",
        "app_secret": "test-app-secret-abc",
        "page_id": "111222333",
        **overrides,
    }
    return MessengerAdapter(cfg)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_defaults():
    adapter = make_adapter()
    assert adapter.channel_id == "messenger"
    assert adapter._token == "EAAG-test-token"
    assert adapter._verify_token == "my-verify-token"
    assert adapter._page_id == "111222333"


def test_construction_env_resolution(monkeypatch):
    monkeypatch.setenv("TEST_FB_TOKEN", "env-resolved-token")
    adapter = MessengerAdapter({"page_access_token": "ENV:TEST_FB_TOKEN"})
    assert adapter._token == "env-resolved-token"


def test_construction_missing_env_returns_empty(monkeypatch):
    monkeypatch.delenv("NO_SUCH_FB_TOKEN", raising=False)
    adapter = MessengerAdapter({"page_access_token": "ENV:NO_SUCH_FB_TOKEN"})
    assert adapter._token == ""


def test_construction_without_app_secret():
    adapter = MessengerAdapter({"page_access_token": "tok"})
    assert adapter._app_secret == ""


def test_construction_without_page_id():
    adapter = MessengerAdapter({"page_access_token": "tok"})
    assert adapter._page_id == ""


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_requires_page_access_token():
    schema = make_adapter().get_config_schema()
    assert "page_access_token" in schema["required"]


def test_config_schema_has_verify_token_default():
    schema = make_adapter().get_config_schema()
    assert schema["properties"]["verify_token"]["default"] == "cortexflow"


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_sets_connected():
    adapter = make_adapter()
    await adapter.connect()
    assert adapter._connected is True


@pytest.mark.asyncio
async def test_connect_raises_if_no_token():
    adapter = make_adapter(page_access_token="")
    with pytest.raises(RuntimeError, match="page_access_token"):
        await adapter.connect()


@pytest.mark.asyncio
async def test_disconnect_clears_connected():
    adapter = make_adapter()
    await adapter.connect()
    await adapter.disconnect()
    assert adapter._connected is False


# ---------------------------------------------------------------------------
# verify_webhook
# ---------------------------------------------------------------------------


def test_verify_webhook_correct_token_returns_challenge():
    adapter = make_adapter(verify_token="secret123")
    result = adapter.verify_webhook("subscribe", "secret123", "challenge-abc")
    assert result == "challenge-abc"


def test_verify_webhook_wrong_token_returns_none():
    adapter = make_adapter(verify_token="secret123")
    result = adapter.verify_webhook("subscribe", "wrong-token", "challenge-abc")
    assert result is None


def test_verify_webhook_wrong_mode_returns_none():
    adapter = make_adapter(verify_token="secret123")
    result = adapter.verify_webhook("unsubscribe", "secret123", "challenge-abc")
    assert result is None


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------


def test_verify_signature_valid():
    adapter = make_adapter(app_secret="my-secret")
    body = b'{"object":"page"}'
    sig = "sha256=" + hmac.new(b"my-secret", body, hashlib.sha256).hexdigest()
    assert adapter.verify_signature(body, sig) is True


def test_verify_signature_invalid():
    adapter = make_adapter(app_secret="my-secret")
    body = b'{"object":"page"}'
    assert adapter.verify_signature(body, "sha256=badhash") is False


def test_verify_signature_wrong_prefix_returns_false():
    adapter = make_adapter(app_secret="my-secret")
    body = b'{"object":"page"}'
    assert adapter.verify_signature(body, "sha1=something") is False


def test_verify_signature_no_app_secret_always_true():
    adapter = make_adapter(app_secret="")
    assert adapter.verify_signature(b"anything", "sha256=badvalue") is True


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_token_returns_none():
    adapter = make_adapter(page_access_token="")
    result = await adapter.send("user-psid-123", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_success_returns_message_id():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"message_id": "mid.abc123"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("user-psid-123", "Hello!")

    assert result == "mid.abc123"


@pytest.mark.asyncio
async def test_send_http_error_returns_none():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("503"))

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("user-psid-123", "hello")

    assert result is None


@pytest.mark.asyncio
async def test_send_payload_has_correct_structure():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"message_id": "mid.xyz"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("psid-999", "Test message")

    call_kwargs = mock_client.post.call_args[1]
    body = call_kwargs["json"]
    assert body["recipient"]["id"] == "psid-999"
    assert body["message"]["text"] == "Test message"
    assert body["messaging_type"] == "RESPONSE"


@pytest.mark.asyncio
async def test_send_access_token_in_params():
    adapter = make_adapter(page_access_token="my-token")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"message_id": "mid.1"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("psid-1", "hi")

    call_kwargs = mock_client.post.call_args[1]
    assert call_kwargs["params"]["access_token"] == "my-token"


# ---------------------------------------------------------------------------
# handle_webhook — non-page object is ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_ignores_non_page_object():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    await adapter.handle_webhook({"object": "user", "entry": []})
    assert dispatched == []


# ---------------------------------------------------------------------------
# handle_webhook — text message dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_dispatches_text_message():
    adapter = make_adapter(page_id="111222333")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    payload = {
        "object": "page",
        "entry": [{
            "id": "111222333",
            "time": 1700000000000,
            "messaging": [{
                "sender": {"id": "user-psid-456"},
                "recipient": {"id": "111222333"},
                "timestamp": 1700000000000,
                "message": {
                    "mid": "mid.abc",
                    "text": "Hello bot!",
                },
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].text == "Hello bot!"
    assert dispatched[0].sender_id == "user-psid-456"
    assert dispatched[0].channel == "messenger"


# ---------------------------------------------------------------------------
# handle_webhook — echo guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_filters_own_page_messages():
    adapter = make_adapter(page_id="111222333")
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    payload = {
        "object": "page",
        "entry": [{
            "id": "111222333",
            "messaging": [{
                "sender": {"id": "111222333"},  # page sending to itself
                "recipient": {"id": "user-psid"},
                "timestamp": 1700000000000,
                "message": {"mid": "m1", "text": "Echo message"},
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_webhook_no_page_id_dispatches_all():
    adapter = make_adapter(page_id="")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "sender-1"},
                "recipient": {"id": "page-1"},
                "timestamp": 1700000000000,
                "message": {"mid": "m1", "text": "Hi"},
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)

    assert len(dispatched) == 1


# ---------------------------------------------------------------------------
# handle_webhook — postback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_dispatches_postback():
    adapter = make_adapter(page_id="page-123")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "user-abc"},
                "recipient": {"id": "page-123"},
                "timestamp": 1700000000000,
                "postback": {
                    "title": "Get Started",
                    "payload": "GET_STARTED",
                },
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert "Get Started" in dispatched[0].text
    assert "GET_STARTED" in dispatched[0].text


@pytest.mark.asyncio
async def test_handle_webhook_postback_title_only():
    adapter = make_adapter(page_id="page-123")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "user-abc"},
                "recipient": {"id": "page-123"},
                "timestamp": 1700000000000,
                "postback": {"title": "Help", "payload": ""},
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].text == "Help"


# ---------------------------------------------------------------------------
# handle_webhook — read event is silently ignored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_ignores_read_events():
    adapter = make_adapter(page_id="page-123")
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "user-abc"},
                "recipient": {"id": "page-123"},
                "timestamp": 1700000000000,
                "read": {"watermark": 1700000000000},
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)
    assert dispatched == []


# ---------------------------------------------------------------------------
# handle_webhook — empty text message skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_empty_text_skipped():
    adapter = make_adapter(page_id="page-123")
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "user-abc"},
                "recipient": {"id": "page-123"},
                "timestamp": 1700000000000,
                "message": {"mid": "m1"},  # no text or attachments
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)
    assert dispatched == []


# ---------------------------------------------------------------------------
# handle_webhook — attachment message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_attachment_message_dispatched():
    adapter = make_adapter(page_id="page-123")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "user-abc"},
                "recipient": {"id": "page-123"},
                "timestamp": 1700000000000,
                "message": {
                    "mid": "m1",
                    "attachments": [{"type": "image", "payload": {"url": "https://example.com/img.png"}}],
                },
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].attachments[0].type == "image"
    assert dispatched[0].attachments[0].url == "https://example.com/img.png"


# ---------------------------------------------------------------------------
# handle_webhook — malformed entry is handled gracefully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_malformed_entry_doesnt_raise():
    adapter = make_adapter()
    # Missing "messaging" key — should not raise
    payload = {"object": "page", "entry": [{"id": "p", "time": 0}]}
    await adapter.handle_webhook(payload)  # no exception


# ---------------------------------------------------------------------------
# handle_webhook — multiple entries and messaging events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_multiple_entries():
    adapter = make_adapter(page_id="page-x")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    def _evt(sender, text):
        return {
            "sender": {"id": sender},
            "recipient": {"id": "page-x"},
            "timestamp": 1700000000000,
            "message": {"mid": f"m-{sender}", "text": text},
        }

    payload = {
        "object": "page",
        "entry": [
            {"messaging": [_evt("user-1", "Hello")]},
            {"messaging": [_evt("user-2", "World")]},
        ],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)

    assert len(dispatched) == 2
    texts = {m.text for m in dispatched}
    assert "Hello" in texts
    assert "World" in texts


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_no_token_returns_false():
    adapter = make_adapter(page_access_token="")
    result = await adapter.ping()
    assert result is False


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
    mock_resp.status_code = 401

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
    mock_client.get = AsyncMock(side_effect=Exception("network error"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.ping()

    assert result is False


# ---------------------------------------------------------------------------
# timestamp handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_timestamp_converted_from_ms():
    adapter = make_adapter(page_id="page-ts")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    ts_ms = 1700000000000
    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "user-ts"},
                "recipient": {"id": "page-ts"},
                "timestamp": ts_ms,
                "message": {"mid": "m1", "text": "ts check"},
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert abs(dispatched[0].timestamp - ts_ms / 1000.0) < 1.0


# ---------------------------------------------------------------------------
# recipient page_id mismatch guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_wrong_recipient_skipped():
    adapter = make_adapter(page_id="my-page-id")
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    payload = {
        "object": "page",
        "entry": [{
            "messaging": [{
                "sender": {"id": "user-abc"},
                "recipient": {"id": "other-page-id"},  # different page
                "timestamp": 1700000000000,
                "message": {"mid": "m1", "text": "Wrong page"},
            }],
        }],
    }
    await adapter.handle_webhook(payload)
    await asyncio.sleep(0)
    assert dispatched == []
