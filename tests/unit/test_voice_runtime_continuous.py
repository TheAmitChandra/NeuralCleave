"""Tests for AgentRuntime._on_voice_transcription — continuous voice pipeline wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.agent.pipeline import PipelineResult, PipelineStreamChunk
from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime() -> AgentRuntime:
    """Minimal AgentRuntime with no real adapters, pipeline, or memory."""
    pipeline = MagicMock()
    session_mgr = MagicMock()
    return AgentRuntime(pipeline=pipeline, session_mgr=session_mgr)


def _make_chunk(*, text: str = "", done: bool = False, error: str | None = None) -> PipelineStreamChunk:
    if done:
        result = PipelineResult(
            response=text,
            model="test",
            provider="test",
            intent="chat",
            task_type="chat",
        )
        return PipelineStreamChunk(done=True, result=result, text=text)
    return PipelineStreamChunk(done=False, text=text, error=error)


class TestOnVoiceTranscription:
    @pytest.mark.asyncio
    async def test_calls_tts_synthesize_on_success(self) -> None:
        """Pipeline produces a reply → TTS is called with the response text."""
        rt = _make_runtime()
        rt._tts = AsyncMock()
        rt._tts.synthesize = AsyncMock(return_value=b"audio")

        async def fake_stream(channel, sender_id, text):
            yield _make_chunk(text="Hi there", done=True)

        rt.process_inbound_text_stream = fake_stream

        await rt._on_voice_transcription("hello")
        rt._tts.synthesize.assert_awaited_once_with("Hi there")

    @pytest.mark.asyncio
    async def test_no_tts_called_when_tts_none(self) -> None:
        """No TTS subsystem → synthesize is never called (no AttributeError)."""
        rt = _make_runtime()
        rt._tts = None

        async def fake_stream(channel, sender_id, text):
            yield _make_chunk(text="reply", done=True)

        rt.process_inbound_text_stream = fake_stream
        await rt._on_voice_transcription("hello")  # should not raise

    @pytest.mark.asyncio
    async def test_error_chunk_aborts_tts(self) -> None:
        """Error chunk in pipeline stream → TTS is NOT called."""
        rt = _make_runtime()
        rt._tts = AsyncMock()
        rt._tts.synthesize = AsyncMock(return_value=b"audio")

        async def fake_stream(channel, sender_id, text):
            yield _make_chunk(error="pipeline failed")

        rt.process_inbound_text_stream = fake_stream
        await rt._on_voice_transcription("hello")
        rt._tts.synthesize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tts_exception_does_not_propagate(self) -> None:
        """TTS failure is swallowed — never raised to the caller."""
        rt = _make_runtime()
        rt._tts = AsyncMock()
        rt._tts.synthesize = AsyncMock(side_effect=RuntimeError("TTS failed"))

        async def fake_stream(channel, sender_id, text):
            yield _make_chunk(text="hello", done=True)

        rt.process_inbound_text_stream = fake_stream
        await rt._on_voice_transcription("hello")  # must not raise

    @pytest.mark.asyncio
    async def test_pipeline_exception_does_not_propagate(self) -> None:
        """Pipeline exception is caught — never raised to the caller."""
        rt = _make_runtime()
        rt._tts = AsyncMock()

        async def fake_stream(channel, sender_id, text):
            raise RuntimeError("pipeline error")
            yield  # make it an async generator

        rt.process_inbound_text_stream = fake_stream
        await rt._on_voice_transcription("hello")  # must not raise

    @pytest.mark.asyncio
    async def test_empty_response_skips_tts(self) -> None:
        """Empty pipeline response → TTS is not called."""
        rt = _make_runtime()
        rt._tts = AsyncMock()
        rt._tts.synthesize = AsyncMock(return_value=b"audio")

        async def fake_stream(channel, sender_id, text):
            yield _make_chunk(text="", done=True)

        rt.process_inbound_text_stream = fake_stream
        await rt._on_voice_transcription("hello")
        rt._tts.synthesize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stream_channel_is_voice(self) -> None:
        """process_inbound_text_stream is called with channel='voice'."""
        rt = _make_runtime()
        rt._tts = None
        captured: dict[str, str] = {}

        async def fake_stream(channel, sender_id, text):
            captured["channel"] = channel
            captured["sender_id"] = sender_id
            captured["text"] = text
            yield _make_chunk(text="ok", done=True)

        rt.process_inbound_text_stream = fake_stream
        await rt._on_voice_transcription("transcribed text")
        assert captured["channel"] == "voice"
        assert captured["sender_id"] == "local_mic"
        assert captured["text"] == "transcribed text"
