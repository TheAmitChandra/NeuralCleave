"""Tests that voice_tts_stream_chunks_total increments per chunk."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import PipelineResult, PipelineStreamChunk
from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream
from neuralcleave.observability.metrics import REGISTRY


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


def _make_runtime(chunks: list[bytes]) -> MagicMock:
    rt = MagicMock()
    rt._stt = MagicMock()
    rt._stt.transcribe = AsyncMock(return_value="hello")

    result = PipelineResult(
        response="reply", model="x", provider="x", intent="chat", task_type="chat"
    )

    async def _stream(channel, sender_id, text, **kw):
        yield PipelineStreamChunk(done=True, result=result)

    rt.process_inbound_text_stream = _stream

    async def _synth_stream(text):
        for c in chunks:
            yield c

    tts = MagicMock()
    tts.synthesize_stream = _synth_stream
    rt._tts = tts
    return rt


class TestStreamHandlerMetricIncrements:
    @pytest.mark.asyncio
    async def test_metric_increments_per_chunk(self) -> None:
        session = _make_session()
        rt = _make_runtime([b"a", b"b", b"c"])

        before = REGISTRY.snapshot()["voice_tts_stream_chunks_total"]["values"].get("", 0.0)

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame_stream(session, b"audio")

        after = REGISTRY.snapshot()["voice_tts_stream_chunks_total"]["values"].get("", 0.0)
        assert after - before == 3.0
