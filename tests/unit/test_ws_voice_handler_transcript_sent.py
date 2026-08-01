"""Tests that _handle_audio_frame_stream() sends audio_transcript JSON frame."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


class TestStreamHandlerTranscriptSent:
    @pytest.mark.asyncio
    async def test_audio_transcript_frame_sent(self) -> None:
        session = _make_session()

        rt = MagicMock()
        rt._stt = MagicMock()
        rt._stt.transcribe = AsyncMock(return_value="hello world")
        rt._tts = None

        async def _stream(channel, sender_id, text, **kw):
            return
            yield

        rt.process_inbound_text_stream = _stream

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"audio")

        text_calls = session.websocket.send_text.call_args_list
        transcript_frames = [
            c for c in text_calls
            if '"audio_transcript"' in (c.args[0] if c.args else "")
        ]
        assert len(transcript_frames) == 1
        payload = json.loads(transcript_frames[0].args[0])
        assert payload["text"] == "hello world"
