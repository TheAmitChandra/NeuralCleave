"""Tests for AudioChunkBuffer utterance segmenter."""

from __future__ import annotations

import struct

from neuralcleave.voice.audio import AudioChunkBuffer
from neuralcleave.voice.vad import VoiceActivityDetector


def _pcm(amplitude: int, samples: int = 160) -> bytes:
    return struct.pack(f"<{samples}h", *([amplitude] * samples))


def _make_buffer(
    *,
    threshold: float = 300.0,
    chunk_ms: int = 30,
    silence_duration_s: float = 0.09,  # 3 × 30 ms chunks
    min_speech_duration_s: float = 0.03,  # 1 chunk
    max_speech_duration_s: float = 1.0,   # ~33 chunks
) -> AudioChunkBuffer:
    vad = VoiceActivityDetector(threshold_rms=threshold)
    return AudioChunkBuffer(
        vad,
        chunk_ms=chunk_ms,
        sample_rate=16_000,
        silence_duration_s=silence_duration_s,
        min_speech_duration_s=min_speech_duration_s,
        max_speech_duration_s=max_speech_duration_s,
    )


SPEECH = _pcm(10000)
SILENCE = _pcm(0)


# ---------------------------------------------------------------------------
# idle state
# ---------------------------------------------------------------------------


class TestIdle:
    def test_silence_before_speech_returns_none(self) -> None:
        buf = _make_buffer()
        assert buf.push(SILENCE) is None

    def test_buffered_chunks_zero_initially(self) -> None:
        buf = _make_buffer()
        assert buf.buffered_chunks == 0

    def test_flush_on_empty_buffer_returns_none(self) -> None:
        buf = _make_buffer()
        assert buf.flush() is None

    def test_reset_on_empty_is_noop(self) -> None:
        buf = _make_buffer()
        buf.reset()  # must not raise


# ---------------------------------------------------------------------------
# accumulation
# ---------------------------------------------------------------------------


class TestAccumulation:
    def test_first_speech_frame_returns_none(self) -> None:
        buf = _make_buffer()
        assert buf.push(SPEECH) is None

    def test_buffered_chunks_increments_on_speech(self) -> None:
        buf = _make_buffer()
        buf.push(SPEECH)
        assert buf.buffered_chunks == 1

    def test_silence_after_speech_returns_none_until_threshold(self) -> None:
        buf = _make_buffer(silence_duration_s=0.09)  # 3 silence chunks trigger end
        buf.push(SPEECH)
        assert buf.push(SILENCE) is None
        assert buf.push(SILENCE) is None


# ---------------------------------------------------------------------------
# utterance completion — silence trigger
# ---------------------------------------------------------------------------


class TestSilenceTrigger:
    def test_silence_after_speech_flushes_utterance(self) -> None:
        buf = _make_buffer(silence_duration_s=0.09)
        buf.push(SPEECH)
        buf.push(SPEECH)
        buf.push(SILENCE)
        buf.push(SILENCE)
        result = buf.push(SILENCE)  # 3rd silence → flush
        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_flushed_bytes_contain_speech_frames(self) -> None:
        buf = _make_buffer(silence_duration_s=0.09)
        buf.push(SPEECH)
        buf.push(SILENCE)
        buf.push(SILENCE)
        result = buf.push(SILENCE)
        assert result is not None
        # Result includes the SPEECH frame bytes
        assert len(result) >= len(SPEECH)

    def test_buffer_resets_after_flush(self) -> None:
        buf = _make_buffer(silence_duration_s=0.09)
        buf.push(SPEECH)
        buf.push(SILENCE)
        buf.push(SILENCE)
        buf.push(SILENCE)  # flush
        assert buf.buffered_chunks == 0
        assert buf.push(SILENCE) is None  # no pending speech


# ---------------------------------------------------------------------------
# utterance completion — max duration trigger
# ---------------------------------------------------------------------------


class TestMaxDurationTrigger:
    def test_max_duration_forces_flush(self) -> None:
        buf = _make_buffer(
            max_speech_duration_s=0.09,  # 3 chunks of 30 ms
            min_speech_duration_s=0.03,
        )
        buf.push(SPEECH)
        buf.push(SPEECH)
        result = buf.push(SPEECH)  # 3rd chunk → force end
        assert result is not None

    def test_buffer_empty_after_max_duration_flush(self) -> None:
        buf = _make_buffer(max_speech_duration_s=0.09, min_speech_duration_s=0.03)
        buf.push(SPEECH)
        buf.push(SPEECH)
        buf.push(SPEECH)
        assert buf.buffered_chunks == 0


# ---------------------------------------------------------------------------
# min speech duration filter
# ---------------------------------------------------------------------------


class TestMinSpeechFilter:
    def test_too_short_utterance_returns_none(self) -> None:
        buf = _make_buffer(
            min_speech_duration_s=0.09,  # 3 chunks required
            silence_duration_s=0.03,
        )
        buf.push(SPEECH)  # 1 speech chunk
        buf.push(SILENCE)  # trigger end immediately
        result = buf.push(SILENCE)
        # Result is None because utterance is too short
        assert result is None

    def test_short_utterance_clears_buffer(self) -> None:
        buf = _make_buffer(min_speech_duration_s=0.09, silence_duration_s=0.03)
        buf.push(SPEECH)
        buf.push(SILENCE)
        buf.push(SILENCE)
        assert buf.buffered_chunks == 0


# ---------------------------------------------------------------------------
# explicit flush and reset
# ---------------------------------------------------------------------------


class TestFlushAndReset:
    def test_flush_returns_buffered_speech(self) -> None:
        buf = _make_buffer(min_speech_duration_s=0.03)
        buf.push(SPEECH)
        buf.push(SPEECH)
        result = buf.flush()
        assert result is not None
        assert len(result) > 0

    def test_flush_clears_buffer(self) -> None:
        buf = _make_buffer(min_speech_duration_s=0.03)
        buf.push(SPEECH)
        buf.flush()
        assert buf.buffered_chunks == 0

    def test_flush_too_short_returns_none(self) -> None:
        buf = _make_buffer(min_speech_duration_s=0.9)
        buf.push(SPEECH)
        assert buf.flush() is None

    def test_reset_discards_buffered_speech(self) -> None:
        buf = _make_buffer()
        buf.push(SPEECH)
        buf.push(SPEECH)
        buf.reset()
        assert buf.buffered_chunks == 0
        assert buf.flush() is None
