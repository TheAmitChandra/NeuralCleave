"""Unit tests for neuralcleave.voice.audio — PCM normaliser."""

from __future__ import annotations

import io
import struct
import wave

import pytest

from neuralcleave.voice.audio import AudioNormaliseError, normalise_to_pcm, normalise_to_wav


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav(
    sample_rate: int = 44_100,
    num_channels: int = 1,
    num_frames: int = 4_410,
    sample_width: int = 2,
) -> bytes:
    """Return minimal valid PCM WAV bytes (silence)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * num_frames * num_channels * sample_width)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# normalise_to_pcm
# ---------------------------------------------------------------------------

def test_normalise_mono_wav_correct_length() -> None:
    """Mono 44.1 kHz WAV → 16 kHz: output length matches expected ratio."""
    pytest.importorskip("soundfile")
    pytest.importorskip("numpy")

    wav = _make_wav(sample_rate=44_100, num_frames=44_100)  # 1 second
    pcm = normalise_to_pcm(wav, target_sr=16_000)

    assert pcm.dtype.name == "float32"
    assert abs(len(pcm) - 16_000) < 20, f"Expected ~16000 samples, got {len(pcm)}"


def test_normalise_stereo_mixes_down_to_mono() -> None:
    """Stereo WAV is collapsed to a single channel."""
    pytest.importorskip("soundfile")
    pytest.importorskip("numpy")

    wav = _make_wav(sample_rate=16_000, num_channels=2, num_frames=16_000)
    pcm = normalise_to_pcm(wav, target_sr=16_000)

    assert pcm.ndim == 1


def test_normalise_no_resample_when_sr_matches() -> None:
    """Input already at target_sr is returned without length change."""
    pytest.importorskip("soundfile")
    pytest.importorskip("numpy")

    wav = _make_wav(sample_rate=16_000, num_frames=8_000)
    pcm = normalise_to_pcm(wav, target_sr=16_000)

    assert len(pcm) == 8_000


def test_normalise_invalid_bytes_raises() -> None:
    """Garbage bytes raise AudioNormaliseError, not a bare exception."""
    pytest.importorskip("soundfile")
    pytest.importorskip("numpy")

    with pytest.raises(AudioNormaliseError):
        normalise_to_pcm(b"not audio at all")


# ---------------------------------------------------------------------------
# normalise_to_wav
# ---------------------------------------------------------------------------

def test_normalise_to_wav_returns_valid_wav() -> None:
    """Output bytes open as a valid WAV file at target_sr."""
    pytest.importorskip("soundfile")
    pytest.importorskip("numpy")

    src = _make_wav(sample_rate=44_100, num_frames=44_100)
    out = normalise_to_wav(src, target_sr=16_000)

    with wave.open(io.BytesIO(out)) as wf:
        assert wf.getframerate() == 16_000
        assert wf.getnchannels() == 1
