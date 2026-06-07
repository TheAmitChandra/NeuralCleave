"""Unit tests for cortexflow.channels.sms — SMSAdapter."""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_handle_inbound_dispatches_handler():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

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

    mock_web = MagicMock()
    mock_web.Response = MagicMock(return_value=MagicMock())

    import sys
    sys.modules["aiohttp"] = MagicMock()
    sys.modules["aiohttp"].web = mock_web

    await a._handle_inbound(request)
    await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].sender_id == "+14155559999"
    assert received[0].text == "Hello SMS"
    assert received[0].channel == "sms"


@pytest.mark.asyncio
async def test_handle_inbound_empty_body_no_dispatch():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    a = SMSAdapter({})
    dispatched = []

    async def _handler(msg):
        dispatched.append(msg)

    a.on_message(_handler)

    request = MagicMock()
    request.post = AsyncMock(return_value={"From": "+1555", "Body": "", "SmsSid": "SM0"})

    mock_web = MagicMock()
    mock_web.Response = MagicMock(return_value=MagicMock())

    import sys
    sys.modules["aiohttp"] = MagicMock()
    sys.modules["aiohttp"].web = mock_web

    await a._handle_inbound(request)
    await asyncio.sleep(0)

    assert dispatched == []
