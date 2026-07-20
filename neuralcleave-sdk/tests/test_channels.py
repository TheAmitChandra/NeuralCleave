"""Unit tests for neuralcleave_sdk.channels — ChannelAdapter / InboundMessage."""

from __future__ import annotations

import pytest
from neuralcleave_sdk import Attachment, ChannelAdapter, InboundMessage


def test_inbound_message_defaults():
    msg = InboundMessage(channel="x", sender_id="u1", sender_name="Alice", text="hi")
    assert msg.attachments == []
    assert msg.thread_id is None
    assert msg.raw == {}
    assert msg.timestamp > 0


def test_attachment_defaults():
    att = Attachment(type="image")
    assert att.url is None
    assert att.data is None


class _EchoAdapter(ChannelAdapter):
    channel_id = "echo"

    def __init__(self, config):
        super().__init__(config)
        self.sent: list[tuple[str, str]] = []
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def send(self, target, text, *, reply_to=None, attachments=None):
        self.sent.append((target, text))
        return "msg-1"


@pytest.mark.asyncio
async def test_subclassed_adapter_connect_disconnect():
    adapter = _EchoAdapter({"enabled": True})
    await adapter.connect()
    assert adapter.connected is True
    await adapter.disconnect()
    assert adapter.connected is False


@pytest.mark.asyncio
async def test_subclassed_adapter_send_returns_message_id():
    adapter = _EchoAdapter({})
    result = await adapter.send("user-1", "hello")
    assert result == "msg-1"
    assert adapter.sent == [("user-1", "hello")]


@pytest.mark.asyncio
async def test_on_message_handler_receives_dispatched_message():
    adapter = _EchoAdapter({})
    received: list[InboundMessage] = []

    async def handler(msg: InboundMessage) -> None:
        received.append(msg)

    adapter.on_message(handler)
    msg = InboundMessage(channel="echo", sender_id="u1", sender_name="Bob", text="hi")
    await adapter._dispatch(msg)

    assert received == [msg]


@pytest.mark.asyncio
async def test_dispatch_without_handler_is_noop():
    adapter = _EchoAdapter({})
    msg = InboundMessage(channel="echo", sender_id="u1", sender_name="Bob", text="hi")
    await adapter._dispatch(msg)  # must not raise


def test_default_config_schema():
    schema = _EchoAdapter({}).get_config_schema()
    assert schema["properties"]["enabled"]["default"] is False


def test_adapter_repr_includes_channel_id():
    assert repr(_EchoAdapter({})) == "_EchoAdapter(channel_id='echo')"


def test_channel_adapter_is_abstract():
    with pytest.raises(TypeError):
        ChannelAdapter({})  # type: ignore[abstract]
