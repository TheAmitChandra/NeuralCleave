"""Unit tests for cortexflow.channels.sms — SMSAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.channels.sms import SMSAdapter

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_channel_id():
    assert SMSAdapter({}).channel_id == "sms"


def test_default_port():
    a = SMSAdapter({})
    assert a._webhook_port == 7434


def test_config_schema_required_fields():
    schema = SMSAdapter({}).get_config_schema()
    assert "account_sid" in schema["required"]
    assert "auth_token" in schema["required"]
    assert "from_number" in schema["required"]


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("TWILIO_SID", "AC123")
    a = SMSAdapter({"account_sid": "ENV:TWILIO_SID"})
    assert a._account_sid == "AC123"


# ---------------------------------------------------------------------------
# send() — Twilio not installed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_returns_none_when_twilio_not_installed(monkeypatch):
    import sys
    # Ensure twilio is not importable
    monkeypatch.setitem(sys.modules, "twilio", None)
    monkeypatch.setitem(sys.modules, "twilio.rest", None)

    a = SMSAdapter({
        "account_sid": "AC123",
        "auth_token": "token",
        "from_number": "+15551234567",
    })
    result = await a.send("+14155559999", "hello")
    assert result is None


# ---------------------------------------------------------------------------
# _handle_inbound — parses TwiML POST
# ---------------------------------------------------------------------------


def _mock_aiohttp_web_module() -> MagicMock:
    mock_aiohttp = MagicMock()
    mock_aiohttp.web.Response = MagicMock(return_value=MagicMock())
    return mock_aiohttp


@pytest.mark.asyncio
async def test_handle_inbound_dispatches_handler():
    import asyncio

    a = SMSAdapter({"from_number": "+1555"})
    received = []

    async def _handler(msg):
        received.append(msg)

    a.on_message(_handler)

    request = MagicMock()
    request.post = AsyncMock(return_value={
        "From": "+14155559999",
        "Body": "Hello SMS",
        "SmsSid": "SM123",
    })

    # monkeypatch.setitem (not direct sys.modules mutation) so the real,
    # installed aiohttp package is restored after this test — a later
    # test in this file exercises connect() against the real aiohttp.web.
    with patch.dict("sys.modules", {"aiohttp": _mock_aiohttp_web_module()}):
        await a._handle_inbound(request)
        await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].sender_id == "+14155559999"
    assert received[0].text == "Hello SMS"
    assert received[0].channel == "sms"


@pytest.mark.asyncio
async def test_handle_inbound_empty_body_no_dispatch():
    import asyncio

    a = SMSAdapter({})
    dispatched = []

    async def _handler(msg):
        dispatched.append(msg)

    a.on_message(_handler)

    request = MagicMock()
    request.post = AsyncMock(return_value={"From": "+1555", "Body": "", "SmsSid": "SM0"})

    with patch.dict("sys.modules", {"aiohttp": _mock_aiohttp_web_module()}):
        await a._handle_inbound(request)
        await asyncio.sleep(0)

    assert dispatched == []


# ---------------------------------------------------------------------------
# connect() / disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_if_aiohttp_not_installed():
    a = SMSAdapter({})
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aiohttp":
            raise ImportError("No module named 'aiohttp'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install aiohttp"):
            await a.connect()


@pytest.mark.asyncio
async def test_connect_binds_real_aiohttp_site_and_disconnect_cleans_up():
    # Uses the real, installed aiohttp — webhook_port=0 lets the OS assign
    # an ephemeral free port so this never collides with anything running.
    a = SMSAdapter({"webhook_port": 0, "webhook_host": "127.0.0.1"})

    await a.connect()
    try:
        assert a._runner is not None
        assert a._site is not None
    finally:
        await a.disconnect()

    assert a._runner is None


@pytest.mark.asyncio
async def test_disconnect_with_no_runner_is_noop():
    a = SMSAdapter({})
    await a.disconnect()  # should not raise


# ---------------------------------------------------------------------------
# send() — Twilio success / failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_success_returns_message_sid():
    a = SMSAdapter({
        "account_sid": "AC123",
        "auth_token": "token",
        "from_number": "+15551234567",
    })

    mock_message = MagicMock()
    mock_message.sid = "SM999"
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create = MagicMock(return_value=mock_message)

    mock_twilio_rest = MagicMock()
    mock_twilio_rest.Client = MagicMock(return_value=mock_client_instance)

    with patch.dict("sys.modules", {"twilio": MagicMock(), "twilio.rest": mock_twilio_rest}):
        result = await a.send("+14155559999", "hello")

    assert result == "SM999"
    mock_client_instance.messages.create.assert_called_once_with(
        body="hello", from_="+15551234567", to="+14155559999",
    )


@pytest.mark.asyncio
async def test_send_twilio_exception_returns_none():
    a = SMSAdapter({
        "account_sid": "AC123",
        "auth_token": "token",
        "from_number": "+15551234567",
    })

    mock_client_instance = MagicMock()
    mock_client_instance.messages.create = MagicMock(side_effect=Exception("Twilio API error"))

    mock_twilio_rest = MagicMock()
    mock_twilio_rest.Client = MagicMock(return_value=mock_client_instance)

    with patch.dict("sys.modules", {"twilio": MagicMock(), "twilio.rest": mock_twilio_rest}):
        result = await a.send("+14155559999", "hello")

    assert result is None
