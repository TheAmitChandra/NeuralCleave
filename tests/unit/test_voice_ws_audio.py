"""Unit tests for the binary audio lane in neuralcleave.gateway.websocket."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    session = Session(websocket=ws)
    return session


def _make_runtime(
    stt_text: str = "hello world",
    tts_audio: bytes | None = b"audio",
) -> MagicMock:
    rt = MagicMock()
    stt = MagicMock()
    stt.transcribe = AsyncMock(return_value=stt_text)
    rt._stt = stt

    tts = MagicMock()
    tts.synthesize = AsyncMock(return_value=tts_audio)
    rt._tts = tts

    async def _stream(channel, sender_id, text):
        chunk = MagicMock()
        chunk.error = None
        chunk.text = "reply text"
        chunk.done = True
        chunk.result = MagicMock()
        chunk.result.response = "reply text"
        yield chunk

    rt.process_inbound_text_stream = _stream
    return rt


# ---------------------------------------------------------------------------
# Session.send_bytes
# ---------------------------------------------------------------------------

class TestSessionSendBytes:
    @pytest.mark.asyncio
    async def test_send_bytes_calls_ws_send_bytes(self) -> None:
        session = _make_session()
        await session.send_bytes(b"\x00\x01\x02")
        session.websocket.send_bytes.assert_awaited_once_with(b"\x00\x01\x02")

    @pytest.mark.asyncio
    async def test_send_bytes_no_op_when_ws_none(self) -> None:
        session = Session()
        session.websocket = None
        await session.send_bytes(b"data")  # must not raise

    @pytest.mark.asyncio
    async def test_send_bytes_swallows_exception(self) -> None:
        session = _make_session()
        session.websocket.send_bytes = AsyncMock(side_effect=OSError("conn reset"))
        await session.send_bytes(b"data")  # must not raise


# ---------------------------------------------------------------------------
# _handle_audio_frame — happy path
# ---------------------------------------------------------------------------

_SILENCE_PASS = [
    patch("neuralcleave.voice.audio.detect_silence", return_value=False),
    patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b),
]


class TestHandleAudioFrameHappyPath:
    @pytest.mark.asyncio
    async def test_transcribes_and_sends_audio_reply(self) -> None:
        session = _make_session()
        rt = _make_runtime(stt_text="hello", tts_audio=b"mp3bytes")
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame(session, b"ogg_audio")
        session.websocket.send_bytes.assert_awaited_once_with(b"mp3bytes")

    @pytest.mark.asyncio
    async def test_sends_audio_transcript_frame(self) -> None:
        session = _make_session()
        rt = _make_runtime(stt_text="hello world", tts_audio=b"mp3")
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame(session, b"ogg")
        text_calls = [
            call for call in session.websocket.send_text.call_args_list
            if '"audio_transcript"' in (call.args[0] if call.args else "")
        ]
        assert len(text_calls) == 1


# ---------------------------------------------------------------------------
# _handle_audio_frame — edge cases / failure paths
# ---------------------------------------------------------------------------

class TestHandleAudioFrameEdgeCases:
    @pytest.mark.asyncio
    async def test_no_runtime_returns_silently(self) -> None:
        session = _make_session()
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=None):
            await _handle_audio_frame(session, b"data")
        session.websocket.send_bytes.assert_not_awaited()
        session.websocket.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_stt_returns_silently(self) -> None:
        session = _make_session()
        rt = MagicMock()
        rt._stt = None
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt):
            await _handle_audio_frame(session, b"data")
        session.websocket.send_bytes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_transcript_does_not_send_reply(self) -> None:
        session = _make_session()
        rt = _make_runtime(stt_text="")
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt):
            await _handle_audio_frame(session, b"silence")
        session.websocket.send_bytes.assert_not_awaited()
        session.websocket.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stt_failure_logs_and_returns(self) -> None:
        session = _make_session()
        rt = MagicMock()
        stt = MagicMock()
        stt.transcribe = AsyncMock(side_effect=RuntimeError("model error"))
        rt._stt = stt
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt):
            await _handle_audio_frame(session, b"bad_audio")
        session.websocket.send_bytes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tts_failure_falls_back_to_text_frame(self) -> None:
        """When TTS raises, the gateway sends a message_done text frame instead."""
        session = _make_session()
        rt = _make_runtime(stt_text="hello")
        rt._tts.synthesize = AsyncMock(side_effect=RuntimeError("TTS down"))
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame(session, b"audio")
        session.websocket.send_bytes.assert_not_awaited()
        text_calls = [
            call for call in session.websocket.send_text.call_args_list
            if '"message_done"' in (call.args[0] if call.args else "")
        ]
        assert len(text_calls) == 1

    @pytest.mark.asyncio
    async def test_no_tts_sends_text_frame(self) -> None:
        """No TTS configured → fall back to message_done text frame."""
        session = _make_session()
        rt = _make_runtime(stt_text="hello", tts_audio=None)
        rt._tts = None
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.voice.audio.detect_silence", return_value=False), \
             patch("neuralcleave.voice.audio.trim_silence", side_effect=lambda b: b):
            await _handle_audio_frame(session, b"audio")
        session.websocket.send_bytes.assert_not_awaited()
        text_calls = [
            call for call in session.websocket.send_text.call_args_list
            if '"message_done"' in (call.args[0] if call.args else "")
        ]
        assert len(text_calls) == 1
