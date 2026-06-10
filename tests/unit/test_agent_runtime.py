"""Unit tests for cortexflow.agent.runtime — AgentRuntime and RuntimeMetrics."""

from __future__ import annotations

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cortexflow.agent.runtime import AgentRuntime, RuntimeMetrics
from cortexflow.channels.base import ChannelAdapter, InboundMessage
from cortexflow.agent.session import SessionManager


# ---------------------------------------------------------------------------
# Stubs / helpers
# ---------------------------------------------------------------------------


def make_inbound(
    text: str = "hello",
    channel: str = "telegram",
    sender_id: str = "user-1",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        sender_name="Alice",
        text=text,
        thread_id=None,
        timestamp=time.time(),
        raw={},
    )


class FakeAdapter(ChannelAdapter):
    channel_id = "telegram"

    def __init__(self):
        super().__init__({})
        self.connected = False
        self.disconnected = False
        self.sent: list[tuple] = []

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True

    async def send(self, target, text, *, reply_to=None, attachments=None):
        self.sent.append((target, text))
        return "sent-id"

    def get_config_schema(self):
        return {}


class FakePipeline:
    def __init__(self, response_text: str = "AI response"):
        self._response = response_text
        self._call_count = 0

    async def run(self, msg, session) -> MagicMock:
        self._call_count += 1
        result = MagicMock()
        result.response = self._response
        result.model = "gemini-2.0-flash"
        result.latency_ms = 250.0
        return result

    @property
    def _router(self):
        r = MagicMock()
        r.generate = AsyncMock(return_value=MagicMock(text="Summary text"))
        return r

    @property
    def _memory(self):
        m = MagicMock()
        ctx = MagicMock()
        ctx.results = []
        m.retrieve = AsyncMock(return_value=ctx)
        return m


def make_runtime(response_text: str = "AI response") -> AgentRuntime:
    pipeline = FakePipeline(response_text)
    sessions = SessionManager()
    adapter = FakeAdapter()
    return AgentRuntime(
        pipeline=pipeline,
        session_mgr=sessions,
        adapters=[adapter],
        gc_interval=9999,
    )


# ---------------------------------------------------------------------------
# RuntimeMetrics
# ---------------------------------------------------------------------------


def test_runtime_metrics_initial_values():
    m = RuntimeMetrics()
    assert m.messages_received == 0
    assert m.messages_sent == 0
    assert m.errors == 0


def test_runtime_metrics_avg_latency_zero_messages():
    m = RuntimeMetrics()
    assert m.avg_latency_ms == 0.0


def test_runtime_metrics_avg_latency_computed():
    m = RuntimeMetrics()
    m.messages_received = 4
    m.pipeline_latency_ms_total = 1000.0
    assert m.avg_latency_ms == 250.0


def test_runtime_metrics_uptime_positive():
    m = RuntimeMetrics()
    assert m.uptime_seconds >= 0.0


# ---------------------------------------------------------------------------
# AgentRuntime construction
# ---------------------------------------------------------------------------


def test_runtime_registers_adapter_on_construction():
    rt = make_runtime()
    assert "telegram" in rt._adapters


def test_runtime_initial_metrics_zero():
    rt = make_runtime()
    assert rt.metrics.messages_received == 0


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_connects_adapter():
    rt = make_runtime()
    await rt.start()
    adapter = rt._adapters["telegram"]
    assert adapter.connected is True
    await rt.stop()


@pytest.mark.asyncio
async def test_stop_disconnects_adapter():
    rt = make_runtime()
    await rt.start()
    await rt.stop()
    adapter = rt._adapters["telegram"]
    assert adapter.disconnected is True


# ---------------------------------------------------------------------------
# Normal message dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_message_increments_counter():
    rt = make_runtime()
    await rt.start()
    msg = make_inbound("hello")
    await rt._on_message(msg)
    assert rt.metrics.messages_received == 1
    await rt.stop()


@pytest.mark.asyncio
async def test_on_message_sends_reply():
    rt = make_runtime("AI says hi")
    await rt.start()
    msg = make_inbound("what's up")
    await rt._on_message(msg)
    adapter = rt._adapters["telegram"]
    assert len(adapter.sent) == 1
    assert adapter.sent[0][1] == "AI says hi"
    await rt.stop()


@pytest.mark.asyncio
async def test_on_message_pipeline_error_sends_sorry():
    pipeline = FakePipeline()
    pipeline.run = AsyncMock(side_effect=RuntimeError("LLM failed"))
    sessions = SessionManager()
    adapter = FakeAdapter()
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, adapters=[adapter])
    await rt.start()

    msg = make_inbound("break things")
    await rt._on_message(msg)

    assert rt.metrics.errors == 1
    assert "wrong" in adapter.sent[0][1].lower()
    await rt.stop()


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_reset_clears_session():
    rt = make_runtime()
    await rt.start()
    # Build up a session first
    session = rt._sessions.get_or_create("telegram", "user-1")
    session.add_turn("user", "some history")
    assert session.turn_count > 0

    msg = make_inbound("/reset")
    await rt._on_message(msg)
    # After reset turn_count should be 0
    assert session.turn_count == 0
    await rt.stop()


@pytest.mark.asyncio
async def test_slash_status_sends_reply():
    rt = make_runtime()
    await rt.start()
    msg = make_inbound("/status")
    await rt._on_message(msg)
    adapter = rt._adapters["telegram"]
    assert any("Status" in sent[1] for sent in adapter.sent)
    await rt.stop()


@pytest.mark.asyncio
async def test_slash_help_sends_reply():
    rt = make_runtime()
    await rt.start()
    msg = make_inbound("/help")
    await rt._on_message(msg)
    adapter = rt._adapters["telegram"]
    assert any("/reset" in sent[1] for sent in adapter.sent)
    await rt.stop()


# ---------------------------------------------------------------------------
# register_adapter after construction
# ---------------------------------------------------------------------------


def test_register_adapter_adds_to_dict():
    pipeline = FakePipeline()
    sessions = SessionManager()
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions)

    class FakeDiscord(FakeAdapter):
        channel_id = "discord"

    rt.register_adapter(FakeDiscord())
    assert "discord" in rt._adapters
