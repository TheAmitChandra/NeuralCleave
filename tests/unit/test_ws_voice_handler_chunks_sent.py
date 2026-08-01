"""Tests that _handle_audio_frame_stream() sends TTS audio chunks via send_bytes."""

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


def _make_runtime(stt_text: str, response: str, chunks: list[bytes]) -> MagicMock:
    rt = MagicMock()
    rt._stt = MagicMock()
    rt._stt.transcribe = AsyncMock(return_value=stt_text)

    result = PipelineResult(
        response=response, model="x", provider="x", intent="chat", task_type="chat"
    )

    async def _stream(channel, sender_id, text, **kw):
        yield PipelineStreamChunk(done=True, result=result)

    rt.process_inbound_text_stream = _stream

    async def _synthesize_stream(text):
        for c in chunks:
            yield c

    tts = MagicMock()
    tts.synthesize_stream = _synthesize_stream
    rt._tts = tts
    return rt


class TestStreamHandlerChunksSent:
    @pytest.mark.asyncio
    async def test_each_chunk_sent_as_bytes(self) -> None:
        session = _make_session()
        audio_chunks = [b"chunk1", b"chunk2", b"chunk3"]
        rt = _make_runtime("hi", "reply", audio_chunks)

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"audio")

        assert session.websocket.send_bytes.await_count == 3
        sent = [c.args[0] for c in session.websocket.send_bytes.call_args_list]
        assert sent == audio_chunks

    @pytest.mark.asyncio
    async def test_no_message_done_when_chunks_sent(self) -> None:
        session = _make_session()
        rt = _make_runtime("hi", "reply", [b"audio"])

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"audio")

        text_calls = session.websocket.send_text.call_args_list
        done_frames = [c for c in text_calls if '"message_done"' in (c.args[0] if c.args else "")]
        assert len(done_frames) == 0
