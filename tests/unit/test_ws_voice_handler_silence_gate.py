"""Tests silence gating in _handle_audio_frame_stream()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


class TestStreamHandlerSilenceGate:
    @pytest.mark.asyncio
    async def test_silent_frame_skips_stt(self) -> None:
        session = _make_session()
        rt = MagicMock()
        rt._stt = MagicMock()
        rt._stt.transcribe = AsyncMock()

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=True):
            await _handle_audio_frame_stream(session, b"silent")

        rt._stt.transcribe.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_silent_passes_trimmed_to_stt(self) -> None:
        session = _make_session()
        rt = MagicMock()
        rt._stt = MagicMock()
        rt._stt.transcribe = AsyncMock(return_value="")
        rt._tts = None

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", return_value=b"trimmed"):
            await _handle_audio_frame_stream(session, b"speech")

        rt._stt.transcribe.assert_awaited_once_with(b"trimmed")
