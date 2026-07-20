"""Unit tests for NeuralCleave.channels.whatsapp — WhatsAppAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.whatsapp import WhatsAppAdapter


def make_adapter(**overrides) -> WhatsAppAdapter:
    cfg = {
        "phone_number_id": "pn-123",
        "access_token": "token-abc",
        "verify_token": "verify-xyz",
        **overrides,
    }
    return WhatsAppAdapter(cfg)


def _mock_client(mock_resp) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=mock_resp)
    client.post = AsyncMock(return_value=mock_resp)
    return client


# ---------------------------------------------------------------------------
# Construction / resolution
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "whatsapp"


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("WA_TOKEN_TEST", "resolved-token")
    adapter = make_adapter(access_token="ENV:WA_TOKEN_TEST")
    assert adapter._access_token == "resolved-token"


def test_resolve_plain_value():
    adapter = make_adapter(phone_number_id="plain-id")
    assert adapter._phone_number_id == "plain-id"


def test_verify_token_defaults_to_NeuralCleave():
    adapter = WhatsAppAdapter({"phone_number_id": "x", "access_token": "y"})
    assert adapter._verify_token == "NeuralCleave"


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "phone_number_id" in schema["required"]
    assert "access_token" in schema["required"]


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_missing_phone_number_id_raises():
    adapter = WhatsAppAdapter({"access_token": "y"})
    with pytest.raises(RuntimeError, match="phone_number_id"):
        await adapter.connect()


@pytest.mark.asyncio
async def test_connect_missing_access_token_raises():
    adapter = WhatsAppAdapter({"phone_number_id": "x"})
    with pytest.raises(RuntimeError, match="access_token"):
        await adapter.connect()


@pytest.mark.asyncio
async def test_connect_invalid_token_raises():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)):
        with pytest.raises(RuntimeError, match="invalid"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_success():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)):
        await adapter.connect()  # should not raise


@pytest.mark.asyncio
async def test_disconnect_does_not_raise():
    adapter = make_adapter()
    await adapter.disconnect()


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_text_message():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"messages": [{"id": "wamid.123"}]})

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)) as client_cls:
        result = await adapter.send("+1555", "hello there")

    assert result == "wamid.123"
    sent_payload = client_cls.return_value.post.call_args[1]["json"]
    assert sent_payload["type"] == "text"
    assert sent_payload["text"]["body"] == "hello there"


@pytest.mark.asyncio
async def test_send_with_reply_to_sets_context():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"messages": [{"id": "wamid.1"}]})

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)) as client_cls:
        await adapter.send("+1555", "reply text", reply_to="wamid.original")

    sent_payload = client_cls.return_value.post.call_args[1]["json"]
    assert sent_payload["context"] == {"message_id": "wamid.original"}


@pytest.mark.asyncio
async def test_send_with_image_attachment():
    from neuralcleave.channels.base import Attachment

    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"messages": [{"id": "wamid.2"}]})

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)) as client_cls:
        await adapter.send(
            "+1555", "a caption",
            attachments=[Attachment(type="image", url="https://example.com/pic.jpg")],
        )

    sent_payload = client_cls.return_value.post.call_args[1]["json"]
    assert sent_payload["type"] == "image"
    assert sent_payload["image"]["link"] == "https://example.com/pic.jpg"
    assert sent_payload["image"]["caption"] == "a caption"


@pytest.mark.asyncio
async def test_send_unknown_attachment_type_falls_back_to_text():
    from neuralcleave.channels.base import Attachment

    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"messages": [{"id": "wamid.3"}]})

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)) as client_cls:
        await adapter.send(
            "+1555", "fallback text",
            attachments=[Attachment(type="location", url="https://example.com/loc")],
        )

    sent_payload = client_cls.return_value.post.call_args[1]["json"]
    assert sent_payload["type"] == "text"
    assert sent_payload["text"]["body"] == "fallback text"


@pytest.mark.asyncio
async def test_send_no_messages_in_response_returns_none():
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"messages": []})

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)):
        result = await adapter.send("+1555", "hello")

    assert result is None


@pytest.mark.asyncio
async def test_send_http_error_returns_none():
    """Regression: send() must return None on HTTP error, not propagate the exception."""
    adapter = make_adapter()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("429 Too Many Requests"))

    with patch("httpx.AsyncClient", return_value=_mock_client(mock_resp)):
        result = await adapter.send("+1555", "hello")

    assert result is None


# ---------------------------------------------------------------------------
# verify_webhook
# ---------------------------------------------------------------------------


def test_verify_webhook_matching_token_returns_challenge():
    adapter = make_adapter()
    result = adapter.verify_webhook("subscribe", "verify-xyz", "challenge-123")
    assert result == "challenge-123"


def test_verify_webhook_wrong_token_returns_none():
    adapter = make_adapter()
    result = adapter.verify_webhook("subscribe", "wrong-token", "challenge-123")
    assert result is None


def test_verify_webhook_wrong_mode_returns_none():
    adapter = make_adapter()
    result = adapter.verify_webhook("unsubscribe", "verify-xyz", "challenge-123")
    assert result is None


# ---------------------------------------------------------------------------
# handle_webhook / _process_value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_webhook_text_message_dispatches():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"wa_id": "1555", "profile": {"name": "Alice"}}],
                    "messages": [{"from": "1555", "type": "text", "text": {"body": "hi"}}],
                }
            }]
        }]
    }

    await adapter.handle_webhook(payload)

    assert len(dispatched) == 1
    assert dispatched[0].sender_id == "1555"
    assert dispatched[0].sender_name == "Alice"
    assert dispatched[0].text == "hi"


@pytest.mark.asyncio
async def test_handle_webhook_image_message_adds_attachment():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "1555", "type": "image",
                        "image": {"mime_type": "image/jpeg", "caption": "a pic"},
                    }],
                }
            }]
        }]
    }

    await adapter.handle_webhook(payload)

    assert len(dispatched) == 1
    assert dispatched[0].attachments[0].type == "image"
    assert dispatched[0].text == "a pic"


@pytest.mark.asyncio
async def test_handle_webhook_sticker_maps_to_image_type():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    payload = {
        "entry": [{"changes": [{"value": {
            "messages": [{"from": "1555", "type": "sticker", "sticker": {}}],
        }}]}]
    }

    await adapter.handle_webhook(payload)

    assert dispatched[0].attachments[0].type == "image"


@pytest.mark.asyncio
async def test_handle_webhook_button_reply_uses_title_as_text():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    payload = {
        "entry": [{"changes": [{"value": {
            "messages": [{
                "from": "1555", "type": "interactive",
                "interactive": {"type": "button_reply", "button_reply": {"title": "Yes"}},
            }],
        }}]}]
    }

    await adapter.handle_webhook(payload)

    assert dispatched[0].text == "Yes"


@pytest.mark.asyncio
async def test_handle_webhook_list_reply_uses_title_as_text():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    payload = {
        "entry": [{"changes": [{"value": {
            "messages": [{
                "from": "1555", "type": "interactive",
                "interactive": {"type": "list_reply", "list_reply": {"title": "Option A"}},
            }],
        }}]}]
    }

    await adapter.handle_webhook(payload)

    assert dispatched[0].text == "Option A"


@pytest.mark.asyncio
async def test_handle_webhook_malformed_payload_does_not_raise():
    adapter = make_adapter()
    await adapter.handle_webhook({"entry": [{"changes": [{"value": "not-a-dict-of-lists"}]}]})


@pytest.mark.asyncio
async def test_handle_webhook_no_contacts_falls_back_to_sender_id():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    payload = {
        "entry": [{"changes": [{"value": {
            "messages": [{"from": "1555", "type": "text", "text": {"body": "hi"}}],
        }}]}]
    }

    await adapter.handle_webhook(payload)

    assert dispatched[0].sender_name == "1555"
