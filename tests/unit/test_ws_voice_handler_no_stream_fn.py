"""Tests _handle_audio_frame_stream() fallback when TTS has no synthesize_stream."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import PipelineResult, PipelineStreamChunk
from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


class TestStreamHandlerNoStreamFn:
    @pytest.mark.asyncio
    async def test_no_stream_fn_sends_message_done(self) -> None:
        session = _make_session()

        result = PipelineResult(
            response="answer", model="x", provider="x", intent="chat", task_type="chat"
        )

        async def _stream(channel, sender_id, text, **kw):
            yield PipelineStreamChunk(done=True, result=result)

        rt = MagicMock()
        rt._stt = MagicMock()
        rt._stt.transcribe = AsyncMock(return_value="question")
        rt.process_inbound_text_stream = _stream

        tts = MagicMock()
        tts.synthesize_stream = None  # explicitly no streaming
        rt._tts = tts

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"audio")

        session.websocket.send_bytes.assert_not_awaited()
        text_calls = session.websocket.send_text.call_args_list
        done_frames = [c for c in text_calls if '"message_done"' in (c.args[0] if c.args else "")]
        assert len(done_frames) == 1
