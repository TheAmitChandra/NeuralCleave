"""Tests for ContinuousVoiceListener.set_silence_duration()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.voice.continuous import ContinuousVoiceListener


def _make_listener(silence_duration_s: float = 0.8) -> ContinuousVoiceListener:
    stt = MagicMock()
    return ContinuousVoiceListener(stt, silence_duration_s=silence_duration_s, chunk_ms=30)


class TestSetSilenceDuration:
    def test_updates_internal_field(self) -> None:
        listener = _make_listener(0.8)
        listener.set_silence_duration(1.5)
        assert listener._silence_duration_s == 1.5

    def test_accepts_float_coercion(self) -> None:
        listener = _make_listener()
        listener.set_silence_duration(2)
        assert isinstance(listener._silence_duration_s, float)

    def test_updates_max_silence_chunks(self) -> None:
        listener = _make_listener()
        listener.set_silence_duration(0.9)
        expected = max(1, int(0.9 * 1000 / 30))
        assert listener._max_silence_chunks == expected

    def test_propagates_to_chunk_buffer(self) -> None:
        listener = _make_listener()
        listener.set_silence_duration(0.6)
        expected = max(1, int(0.6 * 1000 / 30))
        assert listener._chunk_buffer._max_silence_chunks == expected

    def test_minimum_one_chunk(self) -> None:
        listener = _make_listener()
        listener.set_silence_duration(0.001)
        assert listener._max_silence_chunks >= 1

    def test_large_duration_sets_large_chunk_count(self) -> None:
        listener = _make_listener()
        listener.set_silence_duration(5.0)
        assert listener._max_silence_chunks > 10
