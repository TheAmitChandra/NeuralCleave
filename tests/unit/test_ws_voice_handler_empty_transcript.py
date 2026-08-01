"""Tests _handle_audio_frame_stream() with empty STT transcript."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


class TestStreamHandlerEmptyTranscript:
    @pytest.mark.asyncio
    async def test_empty_transcript_no_pipeline_call(self) -> None:
        session = _make_session()

        rt = MagicMock()
        rt._stt = MagicMock()
        rt._stt.transcribe = AsyncMock(return_value="")

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"silence")

        rt.process_inbound_text_stream.assert_not_called()
        session.websocket.send_bytes.assert_not_awaited()
        session.websocket.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_whitespace_only_transcript_skipped(self) -> None:
        session = _make_session()

        rt = MagicMock()
        rt._stt = MagicMock()
        rt._stt.transcribe = AsyncMock(return_value="   ")

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"noise")

        session.websocket.send_bytes.assert_not_awaited()
