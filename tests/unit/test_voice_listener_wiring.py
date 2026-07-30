"""Tests for ContinuousVoiceListener callback wiring and state properties."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.voice.continuous import ContinuousVoiceListener


def _make_listener(**kwargs) -> ContinuousVoiceListener:
    return ContinuousVoiceListener(MagicMock(), **kwargs)


class TestOnTranscriptionCallback:
    def test_callback_registered(self) -> None:
        listener = _make_listener()
        cb = MagicMock()
        listener.on_transcription(cb)
        assert listener._callback is cb

    def test_callback_replaced_by_second_call(self) -> None:
        listener = _make_listener()
        cb1 = MagicMock()
        cb2 = MagicMock()
        listener.on_transcription(cb1)
        listener.on_transcription(cb2)
        assert listener._callback is cb2

    @pytest.mark.asyncio
    async def test_sync_callback_called_on_flush(self) -> None:
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="hello")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)

        called_with: list[str] = []
        listener.on_transcription(lambda t: called_with.append(t))

        await listener._flush_utterance_bytes(b"\x00" * 320)
        assert called_with == ["hello"]

    @pytest.mark.asyncio
    async def test_async_callback_awaited_on_flush(self) -> None:
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="world")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)

        called_with: list[str] = []

        async def _cb(t: str) -> None:
            called_with.append(t)

        listener.on_transcription(_cb)
        await listener._flush_utterance_bytes(b"\x00" * 320)
        assert called_with == ["world"]


class TestListenerStateProperties:
    def test_is_listening_false_initially(self) -> None:
        listener = _make_listener()
        assert listener.is_listening is False

    def test_utterance_count_zero_initially(self) -> None:
        listener = _make_listener()
        assert listener.utterance_count == 0

    def test_last_transcript_empty_initially(self) -> None:
        listener = _make_listener()
        assert listener.last_transcript == ""

    @pytest.mark.asyncio
    async def test_utterance_count_incremented_on_flush(self) -> None:
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="text")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)

        await listener._flush_utterance_bytes(b"\x00" * 320)
        assert listener.utterance_count == 1

    @pytest.mark.asyncio
    async def test_last_transcript_updated_on_flush(self) -> None:
        stt = MagicMock()
        stt.transcribe = AsyncMock(return_value="the transcript")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)

        await listener._flush_utterance_bytes(b"\x00" * 320)
        assert listener.last_transcript == "the transcript"
