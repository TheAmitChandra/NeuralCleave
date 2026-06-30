"""Unit tests for AgentRuntime.process_inbound_text_stream()."""

from __future__ import annotations

import pytest

from cortexflow_ai.agent.pipeline import PipelineResult, PipelineStreamChunk
from cortexflow_ai.agent.runtime import AgentRuntime
from cortexflow_ai.agent.session import SessionManager
from cortexflow_ai.observability.metrics import REGISTRY


class FakeStreamingPipeline:
    """Pipeline whose run_stream() yields a fixed, configurable sequence."""

    def __init__(self, chunks: list[PipelineStreamChunk] | None = None):
        self._chunks = chunks if chunks is not None else [
            PipelineStreamChunk(text="Hel"),
            PipelineStreamChunk(text="lo"),
            PipelineStreamChunk(
                done=True,
                result=PipelineResult(
                    response="Hello", model="gemini-2.5-flash", provider="google",
                    intent="chat", task_type="general", latency_ms=250.0,
                    usage={"input_tokens": 10, "output_tokens": 5},
                ),
            ),
        ]
        self.run_stream_calls = 0

    async def run_stream(self, msg, session):
        self.run_stream_calls += 1
        for c in self._chunks:
            yield c

    # AgentRuntime.start()/from_config() touch these on real pipelines —
    # not needed for these tests since we call process_inbound_text_stream
    # directly without start()/stop().


def make_streaming_runtime(chunks=None) -> AgentRuntime:
    pipeline = FakeStreamingPipeline(chunks)
    sessions = SessionManager()
    return AgentRuntime(pipeline=pipeline, session_mgr=sessions, gc_interval=9999)


async def _collect(stream):
    return [c async for c in stream]


# ---------------------------------------------------------------------------
# Normal streaming path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yields_text_chunks_in_order():
    rt = make_streaming_runtime()
    chunks = await _collect(
        rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi")
    )
    text_chunks = [c for c in chunks if not c.done]
    assert [c.text for c in text_chunks] == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_final_chunk_carries_the_pipeline_result():
    rt = make_streaming_runtime()
    chunks = await _collect(
        rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi")
    )
    final = chunks[-1]
    assert final.done is True
    assert final.result.response == "Hello"


@pytest.mark.asyncio
async def test_updates_metrics_on_successful_stream():
    rt = make_streaming_runtime()
    assert rt.metrics.messages_received == 0
    assert rt.metrics.messages_sent == 0

    await _collect(rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi"))

    assert rt.metrics.messages_received == 1
    assert rt.metrics.messages_sent == 1
    assert rt.metrics.pipeline_latency_ms_total == 250.0


@pytest.mark.asyncio
async def test_records_tokens_total_from_final_usage():
    rt = make_streaming_runtime()
    REGISTRY.get("tokens_total").reset(labels={"model": "gemini-2.5-flash", "direction": "input"})
    REGISTRY.get("tokens_total").reset(labels={"model": "gemini-2.5-flash", "direction": "output"})

    await _collect(rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi"))

    snap = REGISTRY.get("tokens_total").snapshot()
    assert snap["direction=input,model=gemini-2.5-flash"] == 10
    assert snap["direction=output,model=gemini-2.5-flash"] == 5


@pytest.mark.asyncio
async def test_does_not_affect_unread_count():
    """Same guarantee as process_inbound_text(): the streaming path is the
    user's own dashboard/chat-UI traffic, never counted as unread."""
    rt = make_streaming_runtime()
    await _collect(rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi"))
    assert rt.total_unread == 0
    assert rt.get_unread_count("websocket") == 0


# ---------------------------------------------------------------------------
# Mid-stream error path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mid_stream_error_yields_generic_sorry_message():
    chunks = [
        PipelineStreamChunk(text="partial"),
        PipelineStreamChunk(done=True, error="connection dropped"),
    ]
    rt = make_streaming_runtime(chunks)

    result = await _collect(
        rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi")
    )

    assert result[0].text == "partial"
    final = result[-1]
    assert final.done is True
    assert final.error == "Sorry, something went wrong. Please try again."


@pytest.mark.asyncio
async def test_mid_stream_error_increments_error_metrics():
    chunks = [PipelineStreamChunk(done=True, error="boom")]
    rt = make_streaming_runtime(chunks)

    REGISTRY.get("messages_errors_total").reset(labels={"channel": "websocket"})
    await _collect(rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi"))

    assert rt.metrics.errors == 1
    snap = REGISTRY.get("messages_errors_total").snapshot()
    assert snap["channel=websocket"] == 1


@pytest.mark.asyncio
async def test_unexpected_exception_yields_generic_sorry_message():
    rt = make_streaming_runtime()

    async def _boom(msg, session):
        raise RuntimeError("pipeline exploded")
        yield  # pragma: no cover

    rt._pipeline.run_stream = _boom

    result = await _collect(
        rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="hi")
    )

    assert len(result) == 1
    assert result[0].done is True
    assert result[0].error == "Sorry, something went wrong. Please try again."
    assert rt.metrics.errors == 1


# ---------------------------------------------------------------------------
# Slash commands — not streamed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_command_returns_single_done_chunk_without_touching_pipeline():
    rt = make_streaming_runtime()

    result = await _collect(
        rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="/reset")
    )

    assert len(result) == 1
    assert result[0].done is True
    assert "reset" in result[0].result.response.lower()
    assert rt._pipeline.run_stream_calls == 0


@pytest.mark.asyncio
async def test_slash_command_increments_messages_sent():
    rt = make_streaming_runtime()
    await _collect(
        rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="/status")
    )
    assert rt.metrics.messages_sent == 1


@pytest.mark.asyncio
async def test_unrecognized_slash_text_falls_through_to_pipeline():
    rt = make_streaming_runtime()
    result = await _collect(
        rt.process_inbound_text_stream(channel="websocket", sender_id="me", text="/notacommand")
    )
    assert rt._pipeline.run_stream_calls == 1
    assert result[-1].result.response == "Hello"
