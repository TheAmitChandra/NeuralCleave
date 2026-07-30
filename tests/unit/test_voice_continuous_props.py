"""Tests for ContinuousVoiceListener.utterance_count and last_transcript properties."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from neuralcleave.voice.continuous import ContinuousVoiceListener


def _make_stt(text: str = "hello") -> AsyncMock:
    stt = AsyncMock()
    stt.transcribe = AsyncMock(return_value=text)
    return stt


def _min_speech_frames(listener: ContinuousVoiceListener) -> list[bytes]:
    """Return the minimum number of speech frames needed to pass min_speech_chunks."""
    import struct
    n = listener._min_speech_chunks
    return [struct.pack(f"<{listener._chunk_samples}h", *([500] * listener._chunk_samples))] * n


class TestUtteranceCount:
    def test_initial_utterance_count_is_zero(self) -> None:
        listener = ContinuousVoiceListener(_make_stt())
        assert listener.utterance_count == 0

    @pytest.mark.asyncio
    async def test_increments_after_non_empty_transcription(self) -> None:
        stt = _make_stt("hello world")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        assert listener.utterance_count == 1

    @pytest.mark.asyncio
    async def test_does_not_increment_for_empty_transcript(self) -> None:
        stt = _make_stt("")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        assert listener.utterance_count == 0

    @pytest.mark.asyncio
    async def test_increments_multiple_times(self) -> None:
        stt = _make_stt("word")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        await listener._flush_utterance(frames)
        await listener._flush_utterance(frames)
        assert listener.utterance_count == 3

    @pytest.mark.asyncio
    async def test_does_not_increment_on_stt_error(self) -> None:
        stt = AsyncMock()
        stt.transcribe = AsyncMock(side_effect=RuntimeError("STT broken"))
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        assert listener.utterance_count == 0


class TestLastTranscript:
    def test_initial_last_transcript_is_empty(self) -> None:
        listener = ContinuousVoiceListener(_make_stt())
        assert listener.last_transcript == ""

    @pytest.mark.asyncio
    async def test_updated_after_transcription(self) -> None:
        stt = _make_stt("hello NeuralCleave")
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        assert listener.last_transcript == "hello NeuralCleave"

    @pytest.mark.asyncio
    async def test_holds_most_recent_transcript(self) -> None:
        stt = AsyncMock()
        stt.transcribe = AsyncMock(side_effect=["first", "second", "third"])
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        await listener._flush_utterance(frames)
        await listener._flush_utterance(frames)
        assert listener.last_transcript == "third"

    @pytest.mark.asyncio
    async def test_not_updated_for_empty_transcript(self) -> None:
        stt = AsyncMock()
        stt.transcribe = AsyncMock(side_effect=["first", ""])
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        await listener._flush_utterance(frames)
        assert listener.last_transcript == "first"

    @pytest.mark.asyncio
    async def test_not_updated_on_stt_error(self) -> None:
        stt = AsyncMock()
        stt.transcribe = AsyncMock(side_effect=["first", RuntimeError("fail")])
        listener = ContinuousVoiceListener(stt, min_speech_duration_s=0.0)
        frames = _min_speech_frames(listener)
        await listener._flush_utterance(frames)
        await listener._flush_utterance(frames)
        assert listener.last_transcript == "first"
