"""Tests for VoiceActivityDetector — energy and webrtcvad backends."""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

from neuralcleave.voice.vad import VADError, VoiceActivityDetector, _compute_rms


def _pcm(amplitude: int, samples: int = 160) -> bytes:
    """Create a PCM int16 frame with constant amplitude."""
    return struct.pack(f"<{samples}h", *([amplitude] * samples))


# ---------------------------------------------------------------------------
# _compute_rms (module-level helper)
# ---------------------------------------------------------------------------


class TestComputeRms:
    def test_empty_returns_zero(self) -> None:
        assert _compute_rms(b"") == 0.0

    def test_silence_returns_zero(self) -> None:
        rms = _compute_rms(_pcm(0))
        assert rms == pytest.approx(0.0)

    def test_loud_frame_returns_high_rms(self) -> None:
        rms = _compute_rms(_pcm(10000))
        assert rms > 5000

    def test_odd_byte_count_no_crash(self) -> None:
        rms = _compute_rms(b"\x00\x00\x00")  # 3 bytes — 1 complete sample, 1 leftover
        assert isinstance(rms, float)

    def test_numpy_unavailable_falls_back(self) -> None:
        """Without numpy, struct-based fallback must produce the same result."""
        frame = _pcm(1000, samples=16)
        with patch.dict("sys.modules", {"numpy": None}):
            rms_fallback = _compute_rms(frame)
        rms_numpy = _compute_rms(frame)
        assert rms_fallback == pytest.approx(rms_numpy, rel=1e-3)


# ---------------------------------------------------------------------------
# VoiceActivityDetector — construction
# ---------------------------------------------------------------------------


class TestVADConstruction:
    def test_default_backend_is_energy(self) -> None:
        vad = VoiceActivityDetector()
        assert vad.backend == "energy"

    def test_energy_backend_explicit(self) -> None:
        vad = VoiceActivityDetector(backend="energy")
        assert vad.backend == "energy"

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(VADError, match="Unknown VAD backend"):
            VoiceActivityDetector(backend="bogus")

    def test_initial_counters_are_zero(self) -> None:
        vad = VoiceActivityDetector()
        assert vad.speech_frames == 0
        assert vad.silence_frames == 0

    def test_threshold_rms_stored(self) -> None:
        vad = VoiceActivityDetector(threshold_rms=500.0)
        assert vad.threshold_rms == pytest.approx(500.0)

    def test_sample_rate_stored(self) -> None:
        vad = VoiceActivityDetector(sample_rate=8000)
        assert vad.sample_rate == 8000


# ---------------------------------------------------------------------------
# VoiceActivityDetector — energy backend is_speech
# ---------------------------------------------------------------------------


class TestEnergyBackend:
    def test_silent_frame_returns_false(self) -> None:
        vad = VoiceActivityDetector(threshold_rms=300.0)
        assert vad.is_speech(_pcm(0)) is False

    def test_loud_frame_returns_true(self) -> None:
        vad = VoiceActivityDetector(threshold_rms=300.0)
        assert vad.is_speech(_pcm(10000)) is True

    def test_empty_frame_returns_false(self) -> None:
        vad = VoiceActivityDetector()
        assert vad.is_speech(b"") is False

    def test_speech_increments_speech_counter(self) -> None:
        vad = VoiceActivityDetector(threshold_rms=100.0)
        vad.is_speech(_pcm(10000))
        assert vad.speech_frames == 1
        assert vad.silence_frames == 0

    def test_silence_increments_silence_counter(self) -> None:
        vad = VoiceActivityDetector(threshold_rms=100.0)
        vad.is_speech(_pcm(0))
        assert vad.silence_frames == 1
        assert vad.speech_frames == 0

    def test_empty_frame_increments_silence_counter(self) -> None:
        vad = VoiceActivityDetector()
        vad.is_speech(b"")
        assert vad.silence_frames == 1

    def test_counters_accumulate(self) -> None:
        vad = VoiceActivityDetector(threshold_rms=300.0)
        for _ in range(3):
            vad.is_speech(_pcm(10000))
        for _ in range(2):
            vad.is_speech(_pcm(0))
        assert vad.speech_frames == 3
        assert vad.silence_frames == 2

    def test_reset_counters_zeroes_both(self) -> None:
        vad = VoiceActivityDetector()
        vad.is_speech(_pcm(10000))
        vad.is_speech(_pcm(0))
        vad.reset_counters()
        assert vad.speech_frames == 0
        assert vad.silence_frames == 0

    def test_threshold_rms_setter(self) -> None:
        vad = VoiceActivityDetector(threshold_rms=300.0)
        vad.threshold_rms = 100.0
        assert vad.threshold_rms == pytest.approx(100.0)
        assert vad.is_speech(_pcm(200)) is True  # 200 > 100

    def test_compute_rms_does_not_update_counters(self) -> None:
        vad = VoiceActivityDetector()
        vad.compute_rms(_pcm(5000))
        assert vad.speech_frames == 0
        assert vad.silence_frames == 0


# ---------------------------------------------------------------------------
# VoiceActivityDetector — webrtcvad backend (mocked)
# ---------------------------------------------------------------------------


class TestWebRtcVadBackend:
    def test_webrtcvad_missing_raises_vad_error(self) -> None:
        with patch.dict("sys.modules", {"webrtcvad": None}):
            with pytest.raises(VADError, match="webrtcvad"):
                VoiceActivityDetector(backend="webrtcvad")

    def test_webrtcvad_is_speech_calls_underlying_vad(self) -> None:
        fake_vad_instance = MagicMock()
        fake_vad_instance.is_speech.return_value = True
        fake_webrtcvad = MagicMock()
        fake_webrtcvad.Vad.return_value = fake_vad_instance

        with patch.dict("sys.modules", {"webrtcvad": fake_webrtcvad}):
            vad = VoiceActivityDetector(backend="webrtcvad", sample_rate=16_000)
            result = vad.is_speech(_pcm(1000))

        assert result is True
        fake_vad_instance.is_speech.assert_called_once()

    def test_webrtcvad_exception_falls_back_to_energy(self) -> None:
        fake_vad_instance = MagicMock()
        fake_vad_instance.is_speech.side_effect = RuntimeError("bad frame size")
        fake_webrtcvad = MagicMock()
        fake_webrtcvad.Vad.return_value = fake_vad_instance

        with patch.dict("sys.modules", {"webrtcvad": fake_webrtcvad}):
            vad = VoiceActivityDetector(backend="webrtcvad", threshold_rms=100.0)
            # Energy fallback — 10000 amplitude should register as speech
            result = vad.is_speech(_pcm(10000))

        assert result is True
