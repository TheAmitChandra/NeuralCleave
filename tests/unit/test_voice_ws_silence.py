"""Tests for silence preprocessing in _handle_audio_frame (websocket gateway)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame


def _make_session() -> Session:
    session = Session()
    session.websocket = MagicMock()
    session.websocket.send_text = AsyncMock()
    session.websocket.send_bytes = AsyncMock()
    return session


def _make_runtime(*, stt_text: str = "hello") -> MagicMock:
    rt = MagicMock()
    stt = AsyncMock()
    stt.transcribe = AsyncMock(return_value=stt_text)
    rt._stt = stt
    rt._tts = None
    rt.process_inbound_text_stream = AsyncMock()
    return rt


class TestHandleAudioFrameSilenceGating:
    @pytest.mark.asyncio
    async def test_silent_frame_skips_stt(self) -> None:
        """detect_silence returns True → STT is never called."""
        rt = _make_runtime()
        session = _make_session()
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt):
            with patch("neuralcleave.voice.audio.detect_silence", return_value=True):
                await _handle_audio_frame(session, b"silent")
        rt._stt.transcribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_silent_frame_passes_to_stt(self) -> None:
        """detect_silence returns False → trim_silence → STT called."""
        rt = _make_runtime(stt_text="")
        session = _make_session()
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt):
            with patch("neuralcleave.voice.audio.detect_silence", return_value=False):
                with patch("neuralcleave.voice.audio.trim_silence", return_value=b"trimmed"):
                    await _handle_audio_frame(session, b"speech")
        rt._stt.transcribe.assert_called_once_with(b"trimmed")

    @pytest.mark.asyncio
    async def test_silence_utils_exception_falls_through(self) -> None:
        """Audio util ImportError → raw bytes passed to STT unchanged."""
        rt = _make_runtime(stt_text="hello")
        session = _make_session()

        async def fake_stream(channel, sender_id, text):
            from neuralcleave.agent.pipeline import PipelineResult, PipelineStreamChunk
            result = PipelineResult(
                response="hi", model="t", provider="t", intent="chat", task_type="chat"
            )
            yield PipelineStreamChunk(done=True, result=result, text="hi")

        rt.process_inbound_text_stream = fake_stream

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt):
            with patch(
                "neuralcleave.voice.audio.detect_silence",
                side_effect=ImportError("no soundfile"),
            ):
                await _handle_audio_frame(session, b"raw_audio")
        rt._stt.transcribe.assert_called_once_with(b"raw_audio")

    @pytest.mark.asyncio
    async def test_no_runtime_returns_early(self) -> None:
        """No registered runtime → function returns without calling STT."""
        session = _make_session()
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=None):
            await _handle_audio_frame(session, b"audio")  # must not raise

    @pytest.mark.asyncio
    async def test_no_stt_returns_early(self) -> None:
        """Runtime without STT → function returns without error."""
        rt = MagicMock()
        rt._stt = None
        session = _make_session()
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt):
            await _handle_audio_frame(session, b"audio")  # must not raise
