"""Unit tests for cortexflow.agent.runtime — AgentRuntime and RuntimeMetrics."""

from __future__ import annotations

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.agent.runtime import (
    AgentRuntime,
    RuntimeMetrics,
    _build_adapters,
    _make_adapter,
)
from cortexflow_ai.agent.session import SessionManager
from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage
from cortexflow_ai.config import ChannelConfig, CortexFlowConfig

# ---------------------------------------------------------------------------
# Stubs / helpers
# ---------------------------------------------------------------------------


def make_inbound(
    text: str | None = "hello",
    channel: str = "telegram",
    sender_id: str = "user-1",
    attachments: list[Attachment] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        sender_name="Alice",
        text=text,
        attachments=attachments or [],
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
        self.sent.append((target, text, attachments))
        return "sent-id"

    def get_config_schema(self):
        return {}


class FakePipeline:
    def __init__(self, response_text: str = "AI response", usage: dict | None = None):
        self._response = response_text
        self._usage = usage or {}
        self._call_count = 0
        self.last_msg = None

    async def run(self, msg, session) -> MagicMock:
        self._call_count += 1
        self.last_msg = msg
        result = MagicMock()
        result.response = self._response
        result.model = "gemini-2.0-flash"
        result.latency_ms = 250.0
        result.usage = self._usage
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


@pytest.mark.asyncio
async def test_start_initialises_long_term_memory_schema():
    long_term = MagicMock()
    long_term.init_schema = AsyncMock()
    pipeline = FakePipeline()
    sessions = SessionManager()
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, long_term=long_term)

    await rt.start()

    long_term.init_schema.assert_awaited_once()
    await rt.stop()


@pytest.mark.asyncio
async def test_start_without_long_term_does_not_raise():
    rt = make_runtime()  # no long_term injected
    await rt.start()  # should not raise
    await rt.stop()


@pytest.mark.asyncio
async def test_start_swallows_long_term_schema_init_failure():
    long_term = MagicMock()
    long_term.init_schema = AsyncMock(side_effect=RuntimeError("disk full"))
    pipeline = FakePipeline()
    sessions = SessionManager()
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, long_term=long_term)

    await rt.start()  # should not raise — gateway must still come up

    await rt.stop()


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
async def test_on_message_increments_unread_count_for_the_channel():
    rt = make_runtime()
    await rt.start()
    assert rt.get_unread_count("telegram") == 0
    await rt._on_message(make_inbound("hello", channel="telegram"))
    await rt._on_message(make_inbound("again", channel="telegram"))
    assert rt.get_unread_count("telegram") == 2
    assert rt.get_unread_count("discord") == 0  # untouched channel stays 0
    await rt.stop()


@pytest.mark.asyncio
async def test_mark_channel_read_resets_unread_count():
    rt = make_runtime()
    await rt.start()
    await rt._on_message(make_inbound("hello", channel="telegram"))
    assert rt.get_unread_count("telegram") == 1
    rt.mark_channel_read("telegram")
    assert rt.get_unread_count("telegram") == 0
    await rt.stop()


@pytest.mark.asyncio
async def test_total_unread_sums_across_channels():
    rt = make_runtime()
    await rt.start()
    await rt._on_message(make_inbound("a", channel="telegram"))
    await rt._on_message(make_inbound("b", channel="discord"))
    await rt._on_message(make_inbound("c", channel="discord"))
    assert rt.total_unread == 3
    await rt.stop()


@pytest.mark.asyncio
async def test_process_inbound_text_does_not_affect_unread_count():
    """The websocket/chat-UI path must never count as unread — it's the
    user's own traffic, not an external channel message arriving."""
    rt = make_runtime()
    await rt.start()
    await rt.process_inbound_text(channel="websocket", sender_id="me", text="hi")
    assert rt.total_unread == 0
    assert rt.get_unread_count("websocket") == 0
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
async def test_on_message_records_tokens_total_from_usage():
    from cortexflow_ai.observability.metrics import REGISTRY

    pipeline = FakePipeline(usage={"input_tokens": 30, "output_tokens": 12})
    sessions = SessionManager()
    adapter = FakeAdapter()
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, adapters=[adapter])
    await rt.start()

    REGISTRY.get("tokens_total").reset(labels={"model": "gemini-2.0-flash", "direction": "input"})
    REGISTRY.get("tokens_total").reset(labels={"model": "gemini-2.0-flash", "direction": "output"})

    await rt._on_message(make_inbound("token tracking please"))

    snap = REGISTRY.get("tokens_total").snapshot()
    assert snap["direction=input,model=gemini-2.0-flash"] == 30
    assert snap["direction=output,model=gemini-2.0-flash"] == 12
    await rt.stop()


@pytest.mark.asyncio
async def test_on_message_no_usage_does_not_touch_tokens_total():
    from cortexflow_ai.observability.metrics import REGISTRY

    rt = make_runtime("no usage data")
    await rt.start()

    REGISTRY.get("tokens_total").reset(labels={"model": "gemini-2.0-flash", "direction": "input"})

    await rt._on_message(make_inbound("hi"))

    snap = REGISTRY.get("tokens_total").snapshot()
    assert snap.get("direction=input,model=gemini-2.0-flash", 0) == 0
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


# ---------------------------------------------------------------------------
# Voice notes — transcription + TTS reply
# ---------------------------------------------------------------------------


class FakeSTT:
    def __init__(self, transcript: str = "transcribed text") -> None:
        self.transcript = transcript
        self.received: list[bytes] = []

    async def transcribe(self, audio: bytes) -> str:
        self.received.append(audio)
        return self.transcript


class FailingSTT:
    async def transcribe(self, audio: bytes) -> str:
        raise RuntimeError("model not loaded")


class FakeTTS:
    def __init__(self, audio: bytes = b"FAKEAUDIO") -> None:
        self.audio = audio
        self.received_text: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.received_text.append(text)
        return self.audio


def make_voice_runtime(stt=None, tts=None, response_text: str = "AI response") -> tuple[AgentRuntime, FakeAdapter, FakePipeline]:
    pipeline = FakePipeline(response_text)
    sessions = SessionManager()
    adapter = FakeAdapter()
    rt = AgentRuntime(
        pipeline=pipeline,
        session_mgr=sessions,
        adapters=[adapter],
        gc_interval=9999,
        stt=stt,
        tts=tts,
    )
    return rt, adapter, pipeline


@pytest.mark.asyncio
async def test_voice_note_transcribed_before_pipeline_runs():
    stt = FakeSTT("hello from voice")
    rt, adapter, pipeline = make_voice_runtime(stt=stt)
    msg = make_inbound(text=None, attachments=[Attachment(type="audio", data=b"oggbytes")])

    await rt._on_message(msg)

    assert stt.received == [b"oggbytes"]
    assert pipeline.last_msg.text == "hello from voice"


@pytest.mark.asyncio
async def test_voice_note_reply_includes_synthesized_audio():
    stt = FakeSTT("hi there")
    tts = FakeTTS(b"REPLYAUDIO")
    rt, adapter, _ = make_voice_runtime(stt=stt, tts=tts)
    msg = make_inbound(text=None, attachments=[Attachment(type="audio", data=b"oggbytes")])

    await rt._on_message(msg)

    assert len(adapter.sent) == 1
    sent_attachments = adapter.sent[0][2]
    assert sent_attachments is not None
    assert sent_attachments[0].type == "audio"
    assert sent_attachments[0].data == b"REPLYAUDIO"


@pytest.mark.asyncio
async def test_text_message_does_not_trigger_tts_reply():
    tts = FakeTTS(b"SHOULD_NOT_APPEAR")
    rt, adapter, _ = make_voice_runtime(tts=tts)
    msg = make_inbound(text="a normal text message")

    await rt._on_message(msg)

    assert adapter.sent[0][2] is None
    assert tts.received_text == []


@pytest.mark.asyncio
async def test_no_stt_configured_leaves_text_message_unset():
    rt, adapter, pipeline = make_voice_runtime(stt=None)
    msg = make_inbound(text=None, attachments=[Attachment(type="audio", data=b"oggbytes")])

    await rt._on_message(msg)

    # With no STT, the pipeline still runs (text stays empty) rather than crashing.
    assert pipeline.last_msg.text is None


@pytest.mark.asyncio
async def test_stt_failure_does_not_crash_message_handling():
    rt, adapter, pipeline = make_voice_runtime(stt=FailingSTT())
    msg = make_inbound(text=None, attachments=[Attachment(type="audio", data=b"oggbytes")])

    await rt._on_message(msg)

    assert len(adapter.sent) == 1
    assert pipeline.last_msg.text is None


@pytest.mark.asyncio
async def test_attachment_without_data_fetches_via_url(monkeypatch: pytest.MonkeyPatch):
    stt = FakeSTT("fetched transcript")
    rt, adapter, pipeline = make_voice_runtime(stt=stt)
    msg = make_inbound(
        text=None,
        attachments=[Attachment(type="audio", url="https://example.com/voice.ogg")],
    )

    async def fake_fetch(self, url):
        assert url == "https://example.com/voice.ogg"
        return b"fetched-bytes"

    monkeypatch.setattr(AgentRuntime, "_fetch_attachment_bytes", fake_fetch)

    await rt._on_message(msg)

    assert stt.received == [b"fetched-bytes"]
    assert pipeline.last_msg.text == "fetched transcript"


@pytest.mark.asyncio
async def test_no_data_and_failed_url_fetch_returns_false():
    rt, adapter, pipeline = make_voice_runtime(stt=FakeSTT())
    msg = make_inbound(text=None, attachments=[Attachment(type="audio", url="https://example.com/x.ogg")])

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network down"))
        mock_client_cls.return_value = mock_client

        await rt._on_message(msg)

    assert pipeline.last_msg.text is None


# ---------------------------------------------------------------------------
# _fetch_attachment_bytes — real implementation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_attachment_bytes_success():
    rt, _, _ = make_voice_runtime()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"audio-bytes"

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await rt._fetch_attachment_bytes("https://example.com/audio.ogg")

    assert result == b"audio-bytes"


@pytest.mark.asyncio
async def test_fetch_attachment_bytes_failure_returns_none():
    rt, _, _ = make_voice_runtime()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await rt._fetch_attachment_bytes("https://example.com/audio.ogg")

    assert result is None


# ---------------------------------------------------------------------------
# process_inbound_text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_inbound_text_returns_reply_directly():
    rt = make_runtime("web reply")
    result = await rt.process_inbound_text("web", "user-9", "hello there")
    assert result == "web reply"


# ---------------------------------------------------------------------------
# _store_conversation — long-term memory persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reply_for_stores_exchange_to_long_term_memory():
    """Each successful non-slash-command reply must fire a store() task."""
    long_term = MagicMock()
    long_term.store = AsyncMock(return_value=42)

    pipeline = FakePipeline("stored reply")
    rt = AgentRuntime(
        pipeline=pipeline,
        session_mgr=SessionManager(),
        adapters=[FakeAdapter()],
        long_term=long_term,
        gc_interval=9999,
    )
    msg = make_inbound(text="remember this")
    await rt._reply_for(msg)
    await asyncio.sleep(0)  # let the fire-and-forget task run

    long_term.store.assert_awaited_once()
    call_kwargs = long_term.store.call_args[1]
    assert call_kwargs["session_id"] == "telegram"
    assert "remember this" in call_kwargs["content"]
    assert "stored reply" in call_kwargs["content"]
    assert call_kwargs["memory_type"] == "conversation"


@pytest.mark.asyncio
async def test_reply_for_does_not_store_slash_commands():
    """Slash commands are built-in; they should not pollute long-term memory."""
    long_term = MagicMock()
    long_term.store = AsyncMock()

    pipeline = FakePipeline()
    rt = AgentRuntime(
        pipeline=pipeline,
        session_mgr=SessionManager(),
        adapters=[FakeAdapter()],
        long_term=long_term,
        gc_interval=9999,
    )
    msg = make_inbound(text="/help")
    await rt._reply_for(msg)
    await asyncio.sleep(0)

    long_term.store.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_conversation_skipped_when_no_long_term():
    """No long_term injected → _store_conversation is a no-op, no crash."""
    rt = make_runtime("fine")  # no long_term
    msg = make_inbound(text="hello")
    # Should not raise even though _long_term is None
    await rt._reply_for(msg)
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# _send_reply — no adapter registered for channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_reply_no_adapter_for_channel_does_not_raise():
    rt = make_runtime()
    msg = make_inbound(channel="unregistered-channel")
    await rt._send_reply(msg, "some text")  # should not raise


# ---------------------------------------------------------------------------
# _synthesize_reply — exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_reply_tts_failure_falls_back_to_text_only():
    class FailingTTS:
        async def synthesize(self, text):
            raise RuntimeError("TTS down")

    rt, adapter, _ = make_voice_runtime(stt=FakeSTT(), tts=FailingTTS())
    msg = make_inbound(text=None, attachments=[Attachment(type="audio", data=b"oggbytes")])

    await rt._on_message(msg)

    assert len(adapter.sent) == 1
    assert adapter.sent[0][2] is None  # no attachments — synthesis failed gracefully


# ---------------------------------------------------------------------------
# _command_reply — /memory
# ---------------------------------------------------------------------------


class _FakeMemory:
    def __init__(self, results=None):
        self._results = results or []
        self.last_retrieve_kwargs: dict = {}

    async def retrieve(self, query, top_k=5, include_semantic=False, session_id=None, **kwargs):
        self.last_retrieve_kwargs = {"query": query, "top_k": top_k, "session_id": session_id}
        ctx = MagicMock()
        ctx.results = self._results
        return ctx


class _FakeRouter:
    def __init__(self, text="Summary text.", raises=False):
        self._text = text
        self._raises = raises

    async def generate(self, prompt, task_type=None, max_tokens=None):
        if self._raises:
            raise RuntimeError("LLM unavailable")
        result = MagicMock()
        result.text = self._text
        return result


class CommandPipeline:
    """Minimal pipeline stand-in exposing _memory/_router for slash-command tests."""

    def __init__(self, memory_results=None, router_text="Summary text.", router_raises=False):
        self._memory = _FakeMemory(memory_results)
        self._router = _FakeRouter(router_text, router_raises)


def make_command_runtime(**pipeline_kwargs) -> tuple[AgentRuntime, "FakeAdapter"]:
    pipeline = CommandPipeline(**pipeline_kwargs)
    sessions = SessionManager()
    adapter = FakeAdapter()
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, adapters=[adapter], gc_interval=9999)
    return rt, adapter


@pytest.mark.asyncio
async def test_command_memory_with_results():
    rt, adapter = make_command_runtime(memory_results=[MagicMock(content="fact one")])
    msg = make_inbound("/memory")
    await rt._on_message(msg)
    assert "fact one" in adapter.sent[0][1]


@pytest.mark.asyncio
async def test_command_memory_no_results():
    rt, adapter = make_command_runtime(memory_results=[])
    msg = make_inbound("/memory")
    await rt._on_message(msg)
    assert "No memory entries found" in adapter.sent[0][1]


@pytest.mark.asyncio
async def test_command_memory_passes_session_id_to_retrieve():
    """Regression: /memory must pass session_id so short-term Redis tier is included."""
    rt, _ = make_command_runtime(memory_results=[])
    msg = make_inbound("/memory")
    await rt._on_message(msg)

    session = rt._sessions.get("telegram", "user-1")
    retrieved_sid = rt._pipeline._memory.last_retrieve_kwargs.get("session_id")
    assert retrieved_sid is not None
    assert retrieved_sid == session.session_id


# ---------------------------------------------------------------------------
# _command_reply — /compact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_command_compact_not_enough_history():
    rt, adapter = make_command_runtime()
    msg = make_inbound("/compact")
    await rt._on_message(msg)
    assert "Not enough history" in adapter.sent[0][1]


@pytest.mark.asyncio
async def test_command_compact_success():
    rt, adapter = make_command_runtime(router_text="- point one\n- point two")
    session = rt._sessions.get_or_create("telegram", "user-1")
    for i in range(5):
        session.add_turn("user", f"turn {i}")

    msg = make_inbound("/compact")
    await rt._on_message(msg)

    assert "compacted" in adapter.sent[0][1].lower()
    assert "point one" in adapter.sent[0][1]


@pytest.mark.asyncio
async def test_command_compact_router_failure():
    rt, adapter = make_command_runtime(router_raises=True)
    session = rt._sessions.get_or_create("telegram", "user-1")
    for i in range(5):
        session.add_turn("user", f"turn {i}")

    msg = make_inbound("/compact")
    await rt._on_message(msg)

    assert "Compact failed" in adapter.sent[0][1]


# ---------------------------------------------------------------------------
# _command_reply — /voice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_command_voice_on():
    """Regression: /voice must be handled as a command, not sent to the LLM."""
    rt, adapter = make_command_runtime()
    await rt._on_message(make_inbound("/voice on"))
    assert "enabled" in adapter.sent[0][1].lower()


@pytest.mark.asyncio
async def test_command_voice_off():
    rt, adapter = make_command_runtime()
    await rt._on_message(make_inbound("/voice off"))
    assert "disabled" in adapter.sent[0][1].lower()


@pytest.mark.asyncio
async def test_command_voice_invalid_arg():
    rt, adapter = make_command_runtime()
    await rt._on_message(make_inbound("/voice maybe"))
    assert "usage" in adapter.sent[0][1].lower()


# ---------------------------------------------------------------------------
# _command_reply — /model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_command_model_with_name():
    """Regression: /model must be handled as a command, not sent to the LLM."""
    rt, adapter = make_command_runtime()
    await rt._on_message(make_inbound("/model deepseek-coder"))
    assert "deepseek-coder" in adapter.sent[0][1]


@pytest.mark.asyncio
async def test_command_model_no_arg():
    rt, adapter = make_command_runtime()
    await rt._on_message(make_inbound("/model"))
    assert "auto" in adapter.sent[0][1].lower()


# ---------------------------------------------------------------------------
# start() / stop() — adapter connect/disconnect failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_swallows_adapter_connect_failure():
    pipeline = FakePipeline()
    sessions = SessionManager()
    adapter = FakeAdapter()
    adapter.connect = AsyncMock(side_effect=Exception("connect failed"))
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, adapters=[adapter], gc_interval=9999)

    await rt.start()  # should not raise despite the adapter failing to connect

    await rt.stop()


@pytest.mark.asyncio
async def test_stop_swallows_adapter_disconnect_failure():
    pipeline = FakePipeline()
    sessions = SessionManager()
    adapter = FakeAdapter()
    adapter.disconnect = AsyncMock(side_effect=Exception("disconnect failed"))
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, adapters=[adapter], gc_interval=9999)

    await rt.start()
    await rt.stop()  # should not raise despite the adapter failing to disconnect


# ---------------------------------------------------------------------------
# _gc_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gc_loop_removes_idle_sessions():
    pipeline = FakePipeline()
    sessions = SessionManager(idle_timeout=0.0)  # everything is immediately idle
    sessions.get_or_create("telegram", "user-1")
    rt = AgentRuntime(pipeline=pipeline, session_mgr=sessions, gc_interval=0.01)

    await rt.start()
    await asyncio.sleep(0.05)
    await rt.stop()

    assert sessions.active_count == 0


# ---------------------------------------------------------------------------
# _build_adapters / _make_adapter
# ---------------------------------------------------------------------------


def test_make_adapter_telegram():
    adapter = _make_adapter("telegram", {"bot_token": "x"})
    assert adapter is not None
    assert adapter.channel_id == "telegram"


def test_make_adapter_discord():
    adapter = _make_adapter("discord", {"bot_token": "x"})
    assert adapter.channel_id == "discord"


def test_make_adapter_slack():
    adapter = _make_adapter("slack", {"bot_token": "x"})
    assert adapter.channel_id == "slack"


def test_make_adapter_whatsapp():
    adapter = _make_adapter("whatsapp", {"phone_number_id": "x", "access_token": "y"})
    assert adapter.channel_id == "whatsapp"


def test_make_adapter_email():
    adapter = _make_adapter("email", {})
    assert adapter.channel_id == "email"


def test_make_adapter_unknown_channel_returns_none():
    assert _make_adapter("carrier-pigeon", {}) is None


def test_make_adapter_construction_exception_returns_none(monkeypatch):
    import cortexflow_ai.channels.telegram as telegram_module

    def raise_on_init(self, config):
        raise ValueError("bad config")

    monkeypatch.setattr(telegram_module.TelegramAdapter, "__init__", raise_on_init)

    assert _make_adapter("telegram", {}) is None


def test_make_adapter_construction_failure_does_not_log_unknown_channel(monkeypatch, caplog):
    """A recognized adapter that fails to init must NOT emit the 'unknown channel' message."""
    import cortexflow_ai.channels.telegram as telegram_module

    def raise_on_init(self, config):
        raise RuntimeError("missing token")

    monkeypatch.setattr(telegram_module.TelegramAdapter, "__init__", raise_on_init)

    with caplog.at_level(logging.DEBUG, logger="cortexflow_ai.agent.runtime"):
        _make_adapter("telegram", {})

    assert not any("unknown channel" in r.message for r in caplog.records)


def test_build_adapters_skips_disabled_channels():
    cfg = CortexFlowConfig()
    cfg.channels["telegram"] = ChannelConfig(enabled=False, extra={"bot_token": "x"})
    assert _build_adapters(cfg) == []


def test_build_adapters_includes_enabled_channels():
    cfg = CortexFlowConfig()
    cfg.channels["telegram"] = ChannelConfig(enabled=True, extra={"bot_token": "x"})
    cfg.channels["discord"] = ChannelConfig(enabled=True, extra={"bot_token": "y"})
    adapters = _build_adapters(cfg)
    assert {a.channel_id for a in adapters} == {"telegram", "discord"}


def test_build_adapters_empty_config_returns_empty_list():
    assert _build_adapters(CortexFlowConfig()) == []


# ---------------------------------------------------------------------------
# from_config()
# ---------------------------------------------------------------------------


def test_from_config_builds_runtime_with_defaults():
    cfg = CortexFlowConfig()
    rt = AgentRuntime.from_config(cfg)

    assert isinstance(rt, AgentRuntime)
    assert rt._long_term is not None
    assert rt._adapters == {}


def test_from_config_disables_stt_when_voice_stt_is_none():
    cfg = CortexFlowConfig()
    cfg.voice.stt = "none"
    rt = AgentRuntime.from_config(cfg)
    assert rt._stt is None


def test_from_config_disables_tts_when_engine_is_none():
    cfg = CortexFlowConfig()
    cfg.voice.tts_engine = "none"
    rt = AgentRuntime.from_config(cfg)
    assert rt._tts is None


def test_from_config_disables_stt_and_tts_by_default():
    # Voice defaults are "none" — opt-in via config.toml [voice] section.
    cfg = CortexFlowConfig()
    rt = AgentRuntime.from_config(cfg)
    assert rt._stt is None
    assert rt._tts is None


def test_from_config_builds_enabled_channel_adapters():
    cfg = CortexFlowConfig()
    cfg.channels["telegram"] = ChannelConfig(enabled=True, extra={"bot_token": "x"})
    rt = AgentRuntime.from_config(cfg)
    assert "telegram" in rt._adapters


def test_from_config_reflection_unavailable_does_not_crash(monkeypatch):
    import cortexflow_ai.reflection.engine as reflection_module

    def raise_init(self, router):
        raise RuntimeError("reflection broken")

    monkeypatch.setattr(reflection_module.ReflectionEngine, "__init__", raise_init)

    rt = AgentRuntime.from_config(CortexFlowConfig())  # should not raise
    assert isinstance(rt, AgentRuntime)


def test_from_config_stt_unavailable_does_not_crash(monkeypatch):
    import cortexflow_ai.voice.stt as stt_module

    def raise_init(self, model_size="base"):
        raise RuntimeError("stt broken")

    monkeypatch.setattr(stt_module.WhisperSTT, "__init__", raise_init)

    rt = AgentRuntime.from_config(CortexFlowConfig())
    assert rt._stt is None


def test_from_config_tts_unavailable_does_not_crash(monkeypatch):
    import cortexflow_ai.voice.tts as tts_module

    def raise_init(self, **kwargs):
        raise RuntimeError("tts broken")

    monkeypatch.setattr(tts_module.TTSEngine, "__init__", raise_init)

    rt = AgentRuntime.from_config(CortexFlowConfig())
    assert rt._tts is None


def test_from_config_passes_openai_api_key_to_router():
    cfg = CortexFlowConfig()
    cfg.models.openai_api_key = "sk-test-openai-key"
    rt = AgentRuntime.from_config(cfg)
    assert rt._pipeline._router._openai_key == "sk-test-openai-key"


# ---------------------------------------------------------------------------
# _maybe_transcribe — empty transcript after strip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_transcript_after_strip_returns_false():
    stt = FakeSTT("   ")  # whitespace-only transcript
    rt, adapter, pipeline = make_voice_runtime(stt=stt)
    msg = make_inbound(text=None, attachments=[Attachment(type="audio", data=b"oggbytes")])

    await rt._on_message(msg)

    assert pipeline.last_msg.text is None


# ---------------------------------------------------------------------------
# _store_conversation — asyncio guard
# ---------------------------------------------------------------------------


def test_store_conversation_no_event_loop_does_not_raise():
    """Guard: _store_conversation must not propagate RuntimeError when called
    from a thread with no running event loop."""
    import threading

    fake_lt = MagicMock()
    fake_lt.store = AsyncMock()

    rt = AgentRuntime.__new__(AgentRuntime)
    rt._long_term = fake_lt

    errors: list[BaseException] = []

    def _run():
        try:
            rt._store_conversation("channel", "hello", "world")
        except BaseException as exc:
            errors.append(exc)

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    assert errors == [], f"unexpected exception in _store_conversation: {errors[0]}"
