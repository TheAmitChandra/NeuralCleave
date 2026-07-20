"""Unit tests for NeuralCleave.channels.webhook — WebhookAdapter."""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.webhook import WebhookAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapter():
    return WebhookAdapter({"port": 7433, "path": "/webhook", "secret": ""})


@pytest.fixture()
def secured_adapter():
    return WebhookAdapter({"port": 7433, "path": "/webhook", "secret": "test-secret"})


# ---------------------------------------------------------------------------
# Basic metadata
# ---------------------------------------------------------------------------


def test_channel_id():
    assert WebhookAdapter({}).channel_id == "webhook"


def test_default_port():
    a = WebhookAdapter({})
    assert a._port == 7433


def test_custom_port():
    a = WebhookAdapter({"port": 9000})
    assert a._port == 9000


def test_config_schema_has_port():
    schema = WebhookAdapter({}).get_config_schema()
    assert "port" in schema["properties"]


# ---------------------------------------------------------------------------
# send() is inbound-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_returns_none(adapter):
    result = await adapter.send("target", "text")
    assert result is None


# ---------------------------------------------------------------------------
# _handle_post — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_post_dispatches_handler(adapter):
    received = []

    async def _handler(msg):
        received.append(msg)

    adapter.on_message(_handler)

    request = MagicMock()
    request.remote = "127.0.0.1"
    request.json = AsyncMock(return_value={
        "sender_id": "user-1",
        "sender_name": "Alice",
        "text": "Hello webhook",
    })

    mock_web = MagicMock()
    mock_web.json_response = MagicMock(return_value=MagicMock())

    with patch.dict("sys.modules", {"aiohttp": MagicMock(), "aiohttp.web": mock_web}):
        # Need to import web inside the handler
        import sys
        sys.modules["aiohttp"].web = mock_web
        await adapter._handle_post(request)

    # Handler is dispatched via create_task — check the coroutine ran
    import asyncio
    await asyncio.sleep(0)  # let the task schedule
    assert len(received) == 1
    assert received[0].text == "Hello webhook"
    assert received[0].sender_id == "user-1"


@pytest.mark.asyncio
async def test_handle_post_missing_text_returns_400(adapter):
    request = MagicMock()
    request.remote = "127.0.0.1"
    request.json = AsyncMock(return_value={"sender_id": "u1"})

    mock_web = MagicMock()
    mock_web.json_response = MagicMock(return_value="400-response")

    with patch.dict("sys.modules", {"aiohttp": MagicMock(web=mock_web)}):
        await adapter._handle_post(request)

    mock_web.json_response.assert_called_once()
    call_kwargs = mock_web.json_response.call_args
    assert call_kwargs[1].get("status") == 400


@pytest.mark.asyncio
async def test_handle_post_invalid_json_returns_400(adapter):
    request = MagicMock()
    request.remote = "127.0.0.1"
    request.json = AsyncMock(side_effect=Exception("bad json"))

    mock_web = MagicMock()
    mock_web.json_response = MagicMock(return_value="400-response")

    with patch.dict("sys.modules", {"aiohttp": MagicMock(web=mock_web)}):
        await adapter._handle_post(request)

    call_kwargs = mock_web.json_response.call_args
    assert call_kwargs[1].get("status") == 400


# ---------------------------------------------------------------------------
# HMAC signature validation
# ---------------------------------------------------------------------------


def test_valid_signature(secured_adapter):
    body = b'{"text": "hello"}'
    sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    assert secured_adapter._valid_signature(body, sig) is True


def test_invalid_signature(secured_adapter):
    body = b'{"text": "hello"}'
    assert secured_adapter._valid_signature(body, "wrong") is False


# ---------------------------------------------------------------------------
# ENV: secret resolution
# ---------------------------------------------------------------------------


def test_resolve_env_prefix(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "resolved-value")
    a = WebhookAdapter({"secret": "ENV:MY_SECRET"})
    assert a._secret == "resolved-value"


def test_resolve_plain_value():
    a = WebhookAdapter({"secret": "plain-secret"})
    assert a._secret == "plain-secret"


# ---------------------------------------------------------------------------
# connect() / disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_if_aiohttp_not_installed(adapter):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aiohttp":
            raise ImportError("No module named 'aiohttp'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install aiohttp"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_binds_real_aiohttp_site_and_disconnect_cleans_up():
    # Uses the real, installed aiohttp — port=0 lets the OS assign an
    # ephemeral free port so this never collides with anything running.
    a = WebhookAdapter({"port": 0, "host": "127.0.0.1"})

    await a.connect()
    try:
        assert a._runner is not None
        assert a._site is not None
    finally:
        await a.disconnect()

    assert a._runner is None
    assert a._site is None


@pytest.mark.asyncio
async def test_disconnect_with_no_runner_is_noop(adapter):
    await adapter.disconnect()  # should not raise


# ---------------------------------------------------------------------------
# _handle_post — HMAC-secured path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_post_secured_valid_signature_dispatches(secured_adapter):
    import asyncio
    import json

    received = []

    async def _handler(msg):
        received.append(msg)

    secured_adapter.on_message(_handler)

    body = json.dumps({"sender_id": "user-1", "text": "secure hello"}).encode()
    sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    request = MagicMock()
    request.remote = "127.0.0.1"
    request.headers = {"X-Webhook-Signature": sig}
    request.read = AsyncMock(return_value=body)

    mock_web = MagicMock()
    mock_web.json_response = MagicMock(return_value=MagicMock())

    with patch.dict("sys.modules", {"aiohttp": MagicMock(web=mock_web)}):
        await secured_adapter._handle_post(request)
        await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].text == "secure hello"


@pytest.mark.asyncio
async def test_handle_post_secured_invalid_signature_returns_401(secured_adapter):
    body = b'{"sender_id": "u1", "text": "hi"}'

    request = MagicMock()
    request.remote = "127.0.0.1"
    request.headers = {"X-Webhook-Signature": "wrong-signature"}
    request.read = AsyncMock(return_value=body)

    mock_web = MagicMock()
    mock_web.json_response = MagicMock(return_value="401-response")

    with patch.dict("sys.modules", {"aiohttp": MagicMock(web=mock_web)}):
        await secured_adapter._handle_post(request)

    call_kwargs = mock_web.json_response.call_args
    assert call_kwargs[1].get("status") == 401


@pytest.mark.asyncio
async def test_handle_post_secured_valid_signature_invalid_json_returns_400(secured_adapter):
    body = b"not valid json"
    sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    request = MagicMock()
    request.remote = "127.0.0.1"
    request.headers = {"X-Webhook-Signature": sig}
    request.read = AsyncMock(return_value=body)

    mock_web = MagicMock()
    mock_web.json_response = MagicMock(return_value="400-response")

    with patch.dict("sys.modules", {"aiohttp": MagicMock(web=mock_web)}):
        await secured_adapter._handle_post(request)

    call_kwargs = mock_web.json_response.call_args
    assert call_kwargs[1].get("status") == 400


# ---------------------------------------------------------------------------
# _handle_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_health_returns_healthy_status(adapter):
    mock_web = MagicMock()
    mock_web.json_response = MagicMock(side_effect=lambda body: body)

    with patch.dict("sys.modules", {"aiohttp": MagicMock(web=mock_web)}):
        result = await adapter._handle_health(MagicMock())

    assert result == {"status": "healthy", "channel": "webhook"}
