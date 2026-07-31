"""Tests for ContinuousVoiceListener.set_silence_threshold()."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuralcleave.voice.continuous import ContinuousVoiceListener


def _make_listener(threshold: float = 300.0) -> ContinuousVoiceListener:
    stt = MagicMock()
    return ContinuousVoiceListener(stt, silence_threshold_rms=threshold)


class TestSetSilenceThreshold:
    def test_updates_internal_field(self) -> None:
        listener = _make_listener(300.0)
        listener.set_silence_threshold(500.0)
        assert listener._silence_threshold_rms == 500.0

    def test_updates_vad_threshold_rms(self) -> None:
        listener = _make_listener(300.0)
        listener.set_silence_threshold(450.0)
        assert listener._vad.threshold_rms == pytest.approx(450.0)

    def test_accepts_float_coercion(self) -> None:
        listener = _make_listener()
        listener.set_silence_threshold(200)
        assert isinstance(listener._silence_threshold_rms, float)

    def test_zero_threshold_allowed(self) -> None:
        listener = _make_listener()
        listener.set_silence_threshold(0.0)
        assert listener._silence_threshold_rms == 0.0

    def test_high_threshold_stored(self) -> None:
        listener = _make_listener()
        listener.set_silence_threshold(9999.0)
        assert listener._silence_threshold_rms == 9999.0

    def test_vad_and_field_stay_in_sync(self) -> None:
        listener = _make_listener()
        listener.set_silence_threshold(123.4)
        assert listener._silence_threshold_rms == listener._vad.threshold_rms
