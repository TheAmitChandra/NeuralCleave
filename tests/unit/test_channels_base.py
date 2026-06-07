"""Unit tests for cortexflow.channels.base."""

from __future__ import annotations

import time
from typing import Any

import pytest

from cortexflow.channels.base import (
    Attachment,
    ChannelAdapter,
    InboundMessage,
    MessageHandler,
)


# ---------------------------------------------------------------------------
# Concrete stub adapter for testing the abstract base
# ---------------------------------------------------------------------------


class _StubAdapter(ChannelAdapter):
    channel_id = "stub"
    connected = False
    sent: list[tuple[str, str]] = []

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config or {})
        self.connected = False
        self.sent = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def send(self, target: str, text: str, *, reply_to=None, attachments=None) -> str | None:
        self.sent.append((target, text))
        return "msg-id-1"


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------


def test_attachment_defaults() -> None:
    att = Attachment(type="image")
    assert att.url is None
    assert att.data is None
    assert att.filename is None
    assert att.mime_type is None


def test_attachment_full() -> None:
    att = Attachment(type="audio", url="http://example.com/a.ogg", mime_type="audio/ogg")
    assert att.type == "audio"
    assert att.mime_type == "audio/ogg"


# ---------------------------------------------------------------------------
# InboundMessage
# ---------------------------------------------------------------------------


def test_inbound_message_defaults() -> None:
    before = time.time()
    msg = InboundMessage(channel="telegram", sender_id="u1", sender_name="Alice", text="Hello")
    assert msg.attachments == []
    assert msg.thread_id is None
    assert msg.reply_to_id is None
    assert msg.timestamp >= before
    assert msg.raw == {}


def test_inbound_message_with_attachments() -> None:
    att = Attachment(type="image", url="http://x.com/img.png")
    msg = InboundMessage(
        channel="discord",
        sender_id="u2",
        sender_name="Bob",
        text=None,
        attachments=[att],
    )
    assert len(msg.attachments) == 1
    assert msg.attachments[0].url == "http://x.com/img.png"


# ---------------------------------------------------------------------------
# ChannelAdapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_disconnect() -> None:
    adapter = _StubAdapter()
    await adapter.connect()
    assert adapter.connected is True
    await adapter.disconnect()
    assert adapter.connected is False


@pytest.mark.asyncio
async def test_send_returns_message_id() -> None:
    adapter = _StubAdapter()
    mid = await adapter.send("chat-123", "hello")
    assert mid == "msg-id-1"
    assert ("chat-123", "hello") in adapter.sent


@pytest.mark.asyncio
async def test_on_message_handler_dispatched() -> None:
    adapter = _StubAdapter()
    received: list[InboundMessage] = []

    async def handler(msg: InboundMessage) -> None:
        received.append(msg)

    adapter.on_message(handler)
    msg = InboundMessage(channel="stub", sender_id="u", sender_name="User", text="Hi")
    await adapter._dispatch(msg)
    assert len(received) == 1
    assert received[0].text == "Hi"


@pytest.mark.asyncio
async def test_dispatch_no_handler_does_not_raise() -> None:
    adapter = _StubAdapter()
    msg = InboundMessage(channel="stub", sender_id="u", sender_name="User", text="Hi")
    await adapter._dispatch(msg)  # should not raise


def test_get_config_schema_returns_dict() -> None:
    adapter = _StubAdapter()
    schema = adapter.get_config_schema()
    assert schema["type"] == "object"
    assert "properties" in schema


def test_repr() -> None:
    adapter = _StubAdapter()
    assert "stub" in repr(adapter)
