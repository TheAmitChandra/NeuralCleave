"""Tests that ContinuousVoiceListener delegates to VoiceActivityDetector."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.voice.continuous import ContinuousVoiceListener
from neuralcleave.voice.vad import VoiceActivityDetector


def _pcm(amplitude: int, samples: int = 160) -> bytes:
    return struct.pack(f"<{samples}h", *([amplitude] * samples))


def _make_listener(threshold: float = 300.0) -> ContinuousVoiceListener:
    stt = MagicMock()
    stt.transcribe = AsyncMock(return_value="hello")
    return ContinuousVoiceListener(
        stt,
        silence_threshold_rms=threshold,
        silence_duration_s=0.09,
        min_speech_duration_s=0.03,
    )


class TestListenerUsesVAD:
    def test_vad_property_returns_voice_activity_detector(self) -> None:
        listener = _make_listener()
        assert isinstance(listener.vad, VoiceActivityDetector)

    def test_vad_threshold_matches_constructor_arg(self) -> None:
        listener = _make_listener(threshold=500.0)
        assert listener.vad.threshold_rms == pytest.approx(500.0)

    def test_is_speech_delegates_to_vad(self) -> None:
        listener = _make_listener(threshold=300.0)
        loud = _pcm(10000)
        silence = _pcm(0)
        assert listener._is_speech(loud) is True
        assert listener._is_speech(silence) is False

    def test_compute_rms_delegates_to_vad(self) -> None:
        listener = _make_listener()
        frame = _pcm(1000)
        rms_listener = listener._compute_rms(frame)
        rms_vad = listener.vad.compute_rms(frame)
        assert rms_listener == pytest.approx(rms_vad)

    def test_chunk_buffer_uses_same_vad_instance(self) -> None:
        listener = _make_listener()
        assert listener._chunk_buffer._vad is listener._vad

    def test_vad_counts_frames_on_is_speech_calls(self) -> None:
        listener = _make_listener(threshold=300.0)
        listener._is_speech(_pcm(10000))
        listener._is_speech(_pcm(10000))
        listener._is_speech(_pcm(0))
        assert listener.vad.speech_frames == 2
        assert listener.vad.silence_frames == 1


class TestListenerVADProperty:
    def test_changing_threshold_via_vad_affects_is_speech(self) -> None:
        listener = _make_listener(threshold=300.0)
        assert listener._is_speech(_pcm(200)) is False
        listener.vad.threshold_rms = 100.0
        assert listener._is_speech(_pcm(200)) is True
