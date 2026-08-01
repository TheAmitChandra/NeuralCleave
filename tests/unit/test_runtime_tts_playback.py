"""Tests for TTS playback in AgentRuntime._on_voice_transcription."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import PipelineResult, PipelineStreamChunk
from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(tts=None) -> AgentRuntime:
    return AgentRuntime(
        pipeline=MagicMock(),
        session_mgr=MagicMock(),
        tts=tts,
    )


def _done_chunk(response: str) -> PipelineStreamChunk:
    return PipelineStreamChunk(
        done=True,
        result=PipelineResult(
            response=response, model="x", provider="x",
            intent="chat", task_type="chat",
        ),
    )


async def _stream_of(*responses: str):
    for r in responses:
        yield _done_chunk(r)


class TestOnVoiceTranscriptionTts:
    @pytest.mark.asyncio
    async def test_tts_synthesize_called_with_response(self) -> None:
        tts = MagicMock()
        tts.synthesize = AsyncMock(return_value=b"\x00" * 100)
        rt = _make_runtime(tts=tts)

        with patch.object(rt, "process_inbound_text_stream", return_value=_stream_of("hello world")):
            await rt._on_voice_transcription("hi")

        tts.synthesize.assert_called_once_with("hello world")

    @pytest.mark.asyncio
    async def test_no_tts_no_synthesize(self) -> None:
        rt = _make_runtime(tts=None)

        with patch.object(rt, "process_inbound_text_stream", return_value=_stream_of("reply")):
            await rt._on_voice_transcription("hey")

        # No TTS set — nothing to assert beyond no crash

    @pytest.mark.asyncio
    async def test_empty_response_no_tts_call(self) -> None:
        tts = MagicMock()
        tts.synthesize = AsyncMock(return_value=b"\x00" * 100)
        rt = _make_runtime(tts=tts)

        with patch.object(rt, "process_inbound_text_stream", return_value=_stream_of("")):
            await rt._on_voice_transcription("nothing")

        tts.synthesize.assert_not_called()

    @pytest.mark.asyncio
    async def test_tts_synthesis_error_swallowed(self) -> None:
        tts = MagicMock()
        tts.synthesize = AsyncMock(side_effect=RuntimeError("api down"))
        rt = _make_runtime(tts=tts)

        with patch.object(rt, "process_inbound_text_stream", return_value=_stream_of("hello")):
            await rt._on_voice_transcription("test")  # must not raise

    @pytest.mark.asyncio
    async def test_none_audio_no_play(self) -> None:
        tts = MagicMock()
        tts.synthesize = AsyncMock(return_value=None)
        rt = _make_runtime(tts=tts)

        with patch.object(rt, "process_inbound_text_stream", return_value=_stream_of("reply")):
            with patch("neuralcleave.voice.audio.play_audio") as mock_play:
                await rt._on_voice_transcription("test")

        mock_play.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_audio_called_with_synthesized_bytes(self) -> None:
        audio_bytes = b"\xab\xcd" * 50
        tts = MagicMock()
        tts.synthesize = AsyncMock(return_value=audio_bytes)
        rt = _make_runtime(tts=tts)

        play_calls: list[bytes] = []

        def _capture(b: bytes, **kw: object) -> None:
            play_calls.append(b)

        with patch.object(rt, "process_inbound_text_stream", return_value=_stream_of("say this")):
            with patch("neuralcleave.voice.audio.play_audio", side_effect=_capture):
                await rt._on_voice_transcription("speak")

        assert play_calls == [audio_bytes]
