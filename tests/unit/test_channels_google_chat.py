"""Unit tests for neuralcleave.channels.google_chat — GoogleChatAdapter.

Covers:
  - Construction / config
  - ENV: and file-path resolution of service_account_json
  - Inbound event handling (_handle_event)
  - Outbound send()
  - Token caching and refresh (_get_token)
  - connect() / disconnect() lifecycle
  - get_config_schema
  - is_connected
  - Verification-token checks
  - Bot-name echo-loop prevention
  - Thread vs. space target routing
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.google_chat import GoogleChatAdapter

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FAKE_SA = json.dumps({
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key-id-123",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "bot@test-project.iam.gserviceaccount.com",
    "client_id": "123456",
    "token_uri": "https://oauth2.googleapis.com/token",
})


def make_adapter(**overrides) -> GoogleChatAdapter:
    cfg = {
        "service_account_json": _FAKE_SA,
        "webhook_port": 19436,
        "path": "/gchat/messages",
        **overrides,
    }
    return GoogleChatAdapter(cfg)


def make_fake_request(body: dict) -> MagicMock:
    req = MagicMock()
    req.json = AsyncMock(return_value=body)
    return req


def _google_chat_event(
    text: str = "Hello bot!",
    sender_id: str = "users/111",
    sender_name: str = "Alice",
    space_name: str = "spaces/AAA",
    thread_name: str = "spaces/AAA/threads/BBB",
    event_type: str = "MESSAGE",
    token: str | None = None,
) -> dict:
    event: dict = {
        "type": event_type,
        "message": {
            "name": "spaces/AAA/messages/CCC",
            "text": text,
            "sender": {"name": sender_id, "displayName": sender_name, "type": "HUMAN"},
            "thread": {"name": thread_name},
            "space": {"name": space_name},
        },
        "space": {"name": space_name},
    }
    if token is not None:
        event["token"] = token
    return event


def _mock_http_client(response_json: dict | None = None, raise_exc: Exception | None = None):
    mock_resp = MagicMock()
    if raise_exc:
        mock_resp.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value=response_json or {})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "google_chat"


def test_default_webhook_port():
    adapter = GoogleChatAdapter({"service_account_json": _FAKE_SA})
    assert adapter._webhook_port == 7436


def test_default_path():
    adapter = GoogleChatAdapter({"service_account_json": _FAKE_SA})
    assert adapter._path == "/gchat/messages"


def test_custom_port_and_path():
    adapter = make_adapter(webhook_port=9999, path="/custom")
    assert adapter._webhook_port == 9999
    assert adapter._path == "/custom"


def test_verification_token_stored():
    adapter = make_adapter(verification_token="secret123")
    assert adapter._verification_token == "secret123"


def test_bot_name_stored():
    adapter = make_adapter(bot_name="My Bot")
    assert adapter._bot_name == "My Bot"


def test_initial_token_cache_empty():
    adapter = make_adapter()
    assert adapter._cached_token is None
    assert adapter._token_expiry == 0.0


# ---------------------------------------------------------------------------
# _resolve_sa — raw JSON
# ---------------------------------------------------------------------------


def test_resolve_sa_raw_json():
    adapter = make_adapter(service_account_json=_FAKE_SA)
    assert adapter._sa_json == _FAKE_SA


def test_resolve_sa_empty_string():
    adapter = make_adapter(service_account_json="")
    assert adapter._sa_json == ""


# ---------------------------------------------------------------------------
# _resolve_sa — ENV: prefix
# ---------------------------------------------------------------------------


def test_resolve_sa_env_var(monkeypatch):
    monkeypatch.setenv("TEST_SA_JSON", _FAKE_SA)
    adapter = make_adapter(service_account_json="ENV:TEST_SA_JSON")
    assert adapter._sa_json == _FAKE_SA


def test_resolve_sa_env_var_missing(monkeypatch):
    monkeypatch.delenv("MISSING_SA_VAR", raising=False)
    adapter = make_adapter(service_account_json="ENV:MISSING_SA_VAR")
    assert adapter._sa_json == ""


# ---------------------------------------------------------------------------
# _resolve_sa — file path
# ---------------------------------------------------------------------------


def test_resolve_sa_file_path(tmp_path):
    sa_file = tmp_path / "sa.json"
    sa_file.write_text(_FAKE_SA, encoding="utf-8")
    adapter = make_adapter(service_account_json=str(sa_file))
    assert adapter._sa_json == _FAKE_SA


def test_resolve_sa_nonexistent_file_returns_value():
    adapter = make_adapter(service_account_json="/nonexistent/path/sa.json")
    # Falls through to returning the raw value unchanged
    assert "/nonexistent" in adapter._sa_json


# ---------------------------------------------------------------------------
# get_config_schema
# ---------------------------------------------------------------------------


def test_config_schema_required_field():
    schema = make_adapter().get_config_schema()
    assert "service_account_json" in schema["required"]


def test_config_schema_has_webhook_port():
    schema = make_adapter().get_config_schema()
    assert "webhook_port" in schema["properties"]


def test_config_schema_has_verification_token():
    schema = make_adapter().get_config_schema()
    assert "verification_token" in schema["properties"]


def test_config_schema_has_bot_name():
    schema = make_adapter().get_config_schema()
    assert "bot_name" in schema["properties"]


def test_config_schema_default_port():
    schema = make_adapter().get_config_schema()
    assert schema["properties"]["webhook_port"]["default"] == 7436


# ---------------------------------------------------------------------------
# is_connected
# ---------------------------------------------------------------------------


def test_is_connected_false_initially():
    assert not make_adapter().is_connected


@pytest.mark.asyncio
async def test_is_connected_true_after_connect():
    adapter = make_adapter(webhook_port=0)
    await adapter.connect()
    try:
        assert adapter.is_connected
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_is_connected_false_after_disconnect():
    adapter = make_adapter(webhook_port=0)
    await adapter.connect()
    await adapter.disconnect()
    assert not adapter.is_connected


# ---------------------------------------------------------------------------
# connect / disconnect lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_sets_runner():
    adapter = make_adapter(webhook_port=0)
    await adapter.connect()
    try:
        assert adapter._runner is not None
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_disconnect_clears_runner():
    adapter = make_adapter(webhook_port=0)
    await adapter.connect()
    await adapter.disconnect()
    assert adapter._runner is None


@pytest.mark.asyncio
async def test_disconnect_without_connect_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # must not raise


# ---------------------------------------------------------------------------
# _health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200():
    adapter = make_adapter()
    resp = await adapter._health(MagicMock())
    assert resp.status == 200


# ---------------------------------------------------------------------------
# _handle_event — non-MESSAGE event types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_added_to_space_returns_200_no_dispatch():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    event = _google_chat_event(event_type="ADDED_TO_SPACE")
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200
    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_event_removed_from_space_returns_200_no_dispatch():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    event = _google_chat_event(event_type="REMOVED_FROM_SPACE")
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200
    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_event_card_clicked_no_dispatch():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    resp = await adapter._handle_event(make_fake_request({"type": "CARD_CLICKED"}))
    assert resp.status == 200
    assert dispatched == []


# ---------------------------------------------------------------------------
# _handle_event — invalid JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_invalid_json_returns_400():
    adapter = make_adapter()
    req = MagicMock()
    req.json = AsyncMock(side_effect=Exception("not json"))
    resp = await adapter._handle_event(req)
    assert resp.status == 400


# ---------------------------------------------------------------------------
# _handle_event — empty text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_empty_text_returns_200_no_dispatch():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    event = _google_chat_event(text="")
    event["message"]["text"] = ""
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200
    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_event_whitespace_only_text_no_dispatch():
    adapter = make_adapter()
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    event = _google_chat_event()
    event["message"]["text"] = "   "
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200
    assert dispatched == []


# ---------------------------------------------------------------------------
# _handle_event — valid MESSAGE event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_dispatches_inbound_message():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch

    event = _google_chat_event(
        text="ping",
        sender_id="users/42",
        sender_name="Bob",
        thread_name="spaces/AAA/threads/T1",
    )
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200

    await asyncio.sleep(0)
    assert len(dispatched) == 1
    msg = dispatched[0]
    assert msg.text == "ping"
    assert msg.sender_id == "users/42"
    assert msg.sender_name == "Bob"
    assert msg.channel == "google_chat"


@pytest.mark.asyncio
async def test_handle_event_sets_thread_id_from_message():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event(thread_name="spaces/AAA/threads/T99")
    await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert dispatched[0].thread_id == "spaces/AAA/threads/T99"


@pytest.mark.asyncio
async def test_handle_event_falls_back_to_space_when_no_thread():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event()
    del event["message"]["thread"]
    await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert dispatched[0].thread_id == "spaces/AAA"


@pytest.mark.asyncio
async def test_handle_event_raw_contains_full_body():
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event()
    event["custom_field"] = "extra"
    await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert dispatched[0].raw["custom_field"] == "extra"


# ---------------------------------------------------------------------------
# _handle_event — verification token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_verification_token_match_dispatches():
    adapter = make_adapter(verification_token="my-secret")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event(token="my-secret")
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200
    await asyncio.sleep(0)
    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_handle_event_verification_token_mismatch_returns_401():
    adapter = make_adapter(verification_token="my-secret")
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    event = _google_chat_event(token="wrong-token")
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 401
    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_event_no_verification_token_configured_ignores_token_field():
    """If no verification_token configured, skip the check entirely."""
    adapter = make_adapter(verification_token="")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event(token="any-value")
    await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert len(dispatched) == 1


# ---------------------------------------------------------------------------
# _handle_event — bot_name echo prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_skips_bot_own_message():
    adapter = make_adapter(bot_name="NeuralCleave Bot")
    dispatched = []
    adapter._dispatch = AsyncMock(side_effect=lambda m: dispatched.append(m))

    event = _google_chat_event(sender_name="NeuralCleave Bot")
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200
    assert dispatched == []


@pytest.mark.asyncio
async def test_handle_event_does_not_skip_different_user():
    adapter = make_adapter(bot_name="NeuralCleave Bot")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event(sender_name="Alice")
    await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert len(dispatched) == 1


@pytest.mark.asyncio
async def test_handle_event_no_bot_name_all_messages_dispatched():
    adapter = make_adapter(bot_name="")
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event(sender_name="NeuralCleave Bot")
    await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert len(dispatched) == 1


# ---------------------------------------------------------------------------
# _handle_event — argumentText fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_uses_argument_text_when_no_text():
    """Google Chat sometimes puts slash-command text in argumentText."""
    adapter = make_adapter()
    dispatched = []

    async def fake_dispatch(msg):
        dispatched.append(msg)

    adapter._dispatch = fake_dispatch
    event = _google_chat_event()
    event["message"]["text"] = ""
    event["message"]["argumentText"] = "slash arg"
    resp = await adapter._handle_event(make_fake_request(event))
    assert resp.status == 200
    await asyncio.sleep(0)
    assert dispatched[0].text == "slash arg"


# ---------------------------------------------------------------------------
# send — invalid target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_invalid_target_no_spaces_prefix():
    adapter = make_adapter()
    result = await adapter.send("wrong-format", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_no_service_account_returns_none():
    adapter = make_adapter(service_account_json="")
    result = await adapter.send("spaces/AAA", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# send — success (space target)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_to_space_calls_correct_url(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_get_token", AsyncMock(return_value="tok-xyz"))

    mock_client = _mock_http_client({"name": "spaces/AAA/messages/BBB"})
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("spaces/AAA", "Hello!")

    assert result == "spaces/AAA/messages/BBB"
    call_url = mock_client.post.call_args[0][0]
    assert "spaces/AAA/messages" in call_url


@pytest.mark.asyncio
async def test_send_uses_bearer_token_header(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_get_token", AsyncMock(return_value="my-token"))

    mock_client = _mock_http_client({"name": "spaces/AAA/messages/BBB"})
    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("spaces/AAA", "Hi")

    headers = mock_client.post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer my-token"


@pytest.mark.asyncio
async def test_send_payload_contains_text(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_get_token", AsyncMock(return_value="tok"))

    mock_client = _mock_http_client({"name": "spaces/AAA/messages/M"})
    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("spaces/AAA", "Hello world")

    payload = mock_client.post.call_args[1]["json"]
    assert payload["text"] == "Hello world"


# ---------------------------------------------------------------------------
# send — threaded reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_thread_target_includes_thread_in_payload(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_get_token", AsyncMock(return_value="tok"))

    mock_client = _mock_http_client({"name": "spaces/AAA/messages/M"})
    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("spaces/AAA/threads/T1", "Reply!")

    payload = mock_client.post.call_args[1]["json"]
    assert payload.get("thread", {}).get("name") == "spaces/AAA/threads/T1"


@pytest.mark.asyncio
async def test_send_thread_target_posts_to_space_messages_url(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_get_token", AsyncMock(return_value="tok"))

    mock_client = _mock_http_client({"name": "spaces/AAA/messages/M"})
    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.send("spaces/AAA/threads/T1", "Reply!")

    url = mock_client.post.call_args[0][0]
    assert "spaces/AAA/messages" in url


# ---------------------------------------------------------------------------
# send — HTTP failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_http_error_returns_none(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter, "_get_token", AsyncMock(return_value="tok"))

    mock_client = _mock_http_client(raise_exc=Exception("503"))
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.send("spaces/AAA", "Hello")

    assert result is None


@pytest.mark.asyncio
async def test_send_token_none_returns_none():
    adapter = make_adapter()
    adapter._cached_token = None

    with patch.object(adapter, "_get_token", AsyncMock(return_value=None)):
        result = await adapter.send("spaces/AAA", "Hi")

    assert result is None


# ---------------------------------------------------------------------------
# _get_token — no service account
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_token_empty_sa_returns_none():
    adapter = make_adapter(service_account_json="")
    result = await adapter._get_token()
    assert result is None


@pytest.mark.asyncio
async def test_get_token_invalid_json_returns_none():
    adapter = make_adapter(service_account_json="not-json")
    result = await adapter._get_token()
    assert result is None


# ---------------------------------------------------------------------------
# _get_token — caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_token_returns_cache_when_valid():
    adapter = make_adapter()
    adapter._cached_token = "cached-token"
    adapter._token_expiry = time.time() + 3600

    with patch("httpx.AsyncClient") as mock_cls:
        result = await adapter._get_token()

    assert result == "cached-token"
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_get_token_refreshes_when_expired():
    adapter = make_adapter()
    adapter._cached_token = "old-token"
    adapter._token_expiry = time.time() - 1  # expired

    mock_client = _mock_http_client({"access_token": "new-token", "expires_in": 3600})
    mock_key = MagicMock()
    mock_key.sign.return_value = b"fake-sig"

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("cryptography.hazmat.primitives.serialization.load_pem_private_key", return_value=mock_key),
    ):
        result = await adapter._get_token()

    assert result == "new-token"
    assert adapter._cached_token == "new-token"


@pytest.mark.asyncio
async def test_get_token_stores_expiry():
    adapter = make_adapter()
    adapter._token_expiry = 0.0

    mock_client = _mock_http_client({"access_token": "tok", "expires_in": 7200})
    mock_key = MagicMock()
    mock_key.sign.return_value = b"fake-sig"
    before = time.time()

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("cryptography.hazmat.primitives.serialization.load_pem_private_key", return_value=mock_key),
    ):
        await adapter._get_token()

    assert adapter._token_expiry >= before + 7200 - 1


@pytest.mark.asyncio
async def test_get_token_http_error_returns_none():
    adapter = make_adapter()
    adapter._token_expiry = 0.0

    mock_client = _mock_http_client(raise_exc=Exception("401"))
    mock_key = MagicMock()
    mock_key.sign.return_value = b"fake-sig"

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("cryptography.hazmat.primitives.serialization.load_pem_private_key", return_value=mock_key),
    ):
        result = await adapter._get_token()

    assert result is None


@pytest.mark.asyncio
async def test_get_token_crypto_error_returns_none():
    """If cryptography raises (e.g. bad key format), token returns None."""
    adapter = make_adapter()
    adapter._token_expiry = 0.0

    with patch("cryptography.hazmat.primitives.serialization.load_pem_private_key", side_effect=ValueError("bad key")):
        result = await adapter._get_token()

    assert result is None


# ---------------------------------------------------------------------------
# _get_token — JWT construction details
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_token_jwt_sent_as_assertion():
    """The token exchange must POST with grant_type and assertion fields."""
    adapter = make_adapter()
    adapter._token_expiry = 0.0

    mock_client = _mock_http_client({"access_token": "tok-jwt", "expires_in": 3600})
    mock_key = MagicMock()
    mock_key.sign.return_value = b"fake-sig-bytes"

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("cryptography.hazmat.primitives.serialization.load_pem_private_key", return_value=mock_key),
    ):
        await adapter._get_token()

    call_kwargs = mock_client.post.call_args[1]["data"]
    assert call_kwargs["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    assert "assertion" in call_kwargs


@pytest.mark.asyncio
async def test_get_token_posts_to_correct_url():
    adapter = make_adapter()
    adapter._token_expiry = 0.0

    mock_client = _mock_http_client({"access_token": "tok", "expires_in": 3600})
    mock_key = MagicMock()
    mock_key.sign.return_value = b"s"

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("cryptography.hazmat.primitives.serialization.load_pem_private_key", return_value=mock_key),
    ):
        await adapter._get_token()

    url = mock_client.post.call_args[0][0]
    assert "oauth2.googleapis.com/token" in url


# ---------------------------------------------------------------------------
# on_message / _dispatch wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_message_handler_called_on_event():
    adapter = make_adapter()
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message(handler)
    event = _google_chat_event(text="test msg")
    await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert len(received) == 1
    assert received[0].text == "test msg"


@pytest.mark.asyncio
async def test_no_handler_registered_does_not_crash():
    adapter = make_adapter()
    adapter._handler = None
    event = _google_chat_event()
    resp = await adapter._handle_event(make_fake_request(event))
    await asyncio.sleep(0)
    assert resp.status == 200


# ---------------------------------------------------------------------------
# Multiple rapid messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_messages_all_dispatched():
    adapter = make_adapter()
    received = []

    async def handler(msg):
        received.append(msg)

    adapter.on_message(handler)

    for i in range(5):
        event = _google_chat_event(text=f"msg {i}")
        await adapter._handle_event(make_fake_request(event))

    await asyncio.sleep(0)
    assert len(received) == 5
    texts = [m.text for m in received]
    for i in range(5):
        assert f"msg {i}" in texts
