"""Tests that _handle_audio_frame_stream() calls STT with the audio bytes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


def _make_runtime(stt_text: str = "hello") -> MagicMock:
    rt = MagicMock()
    stt = MagicMock()
    stt.transcribe = AsyncMock(return_value=stt_text)
    rt._stt = stt
    rt._tts = None

    async def _stream(channel, sender_id, text, **kw):
        return
        yield  # make it an async generator

    rt.process_inbound_text_stream = _stream
    return rt


class TestStreamHandlerSttCalled:
    @pytest.mark.asyncio
    async def test_stt_transcribe_called_with_audio(self) -> None:
        session = _make_session()
        rt = _make_runtime(stt_text="")
        audio = b"raw_audio_bytes"

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, audio)

        rt._stt.transcribe.assert_awaited_once_with(audio)
