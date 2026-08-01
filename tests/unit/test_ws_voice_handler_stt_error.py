"""Tests _handle_audio_frame_stream() swallows STT errors gracefully."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


class TestStreamHandlerSttError:
    @pytest.mark.asyncio
    async def test_stt_error_returns_silently(self) -> None:
        session = _make_session()

        rt = MagicMock()
        rt._stt = MagicMock()
        rt._stt.transcribe = AsyncMock(side_effect=RuntimeError("model error"))

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"bad_audio")  # must not raise

        session.websocket.send_bytes.assert_not_awaited()
        session.websocket.send_text.assert_not_awaited()
