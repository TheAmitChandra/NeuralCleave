"""Unit tests for detect_silence() and trim_silence() audio utilities."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np

from neuralcleave.voice.audio import detect_silence, trim_silence

# ---------------------------------------------------------------------------
# detect_silence
# ---------------------------------------------------------------------------


class TestDetectSilence:
    def test_returns_true_for_zero_pcm(self) -> None:
        """Flat-zero PCM is silence."""
        pcm = np.zeros(16_000, dtype=np.float32)
        with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
            assert detect_silence(b"dummy") is True

    def test_returns_false_for_loud_pcm(self) -> None:
        """PCM amplitude 0.5 → int16 RMS ≈ 16384, well above threshold 300."""
        pcm = np.full(1_600, 0.5, dtype=np.float32)
        with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
            assert detect_silence(b"dummy") is False

    def test_returns_true_on_normalise_error(self) -> None:
        """Any decode / normalise exception → treat frame as silence."""
        with patch("neuralcleave.voice.audio.normalise_to_pcm", side_effect=RuntimeError("fail")):
            assert detect_silence(b"bad") is True

    def test_custom_threshold_not_silence(self) -> None:
        """pcm 0.01 → RMS ≈ 327 > threshold 200 → not silence."""
        pcm = np.full(1_000, 0.01, dtype=np.float32)
        with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
            assert detect_silence(b"dummy", threshold_rms=200.0) is False

    def test_custom_threshold_is_silence(self) -> None:
        """pcm 0.001 → RMS ≈ 33 < threshold 100 → silence."""
        pcm = np.full(1_000, 0.001, dtype=np.float32)
        with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
            assert detect_silence(b"dummy", threshold_rms=100.0) is True


# ---------------------------------------------------------------------------
# trim_silence
# ---------------------------------------------------------------------------


class TestTrimSilence:
    def test_returns_original_when_all_silence(self) -> None:
        """All-zero PCM has no speech frames → return original bytes unchanged."""
        pcm = np.zeros(16_000, dtype=np.float32)
        with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
            result = trim_silence(b"original_raw")
        assert result == b"original_raw"

    def test_returns_original_on_normalise_error(self) -> None:
        """Decode failure → fall back to original bytes."""
        with patch("neuralcleave.voice.audio.normalise_to_pcm", side_effect=RuntimeError("fail")):
            result = trim_silence(b"raw_audio")
        assert result == b"raw_audio"

    def test_returns_wav_when_soundfile_available(self) -> None:
        """Mocked soundfile: trim_silence returns bytes written by sf.write."""
        pcm = np.full(16_000, 0.5, dtype=np.float32)
        sentinel = b"RIFF____WAV_SENTINEL"

        fake_sf = MagicMock()

        def _write(buf, data, sr, format, subtype):  # noqa: A002
            buf.write(sentinel)

        fake_sf.write.side_effect = _write
        sys.modules["soundfile"] = fake_sf
        try:
            with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
                result = trim_silence(b"dummy")
        finally:
            sys.modules.pop("soundfile", None)

        assert result == sentinel

    def test_returns_original_when_soundfile_missing(self) -> None:
        """If soundfile is not installed, trim_silence returns the original bytes."""
        pcm = np.full(16_000, 0.5, dtype=np.float32)
        sys.modules.pop("soundfile", None)
        with patch("neuralcleave.voice.audio.normalise_to_pcm", return_value=pcm):
            result = trim_silence(b"fallback_bytes")
        # soundfile ImportError is caught → original returned
        assert result == b"fallback_bytes"
