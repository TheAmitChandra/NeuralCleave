"""Audio normalisation utilities for the voice pipeline.

Converts raw audio bytes (OGG/Opus, MP3, WAV, WebM) into a 16 kHz
mono float32 PCM array that faster-whisper ingests directly. This avoids
writing a temp file and re-encoding when the caller already has bytes in
memory — particularly useful for the WebSocket audio lane where small
500 ms chunks arrive as Blobs from MediaRecorder.

The output array is suitable for direct use with:
    WhisperModel.transcribe(audio_array, sampling_rate=16000)

Falls back gracefully: if soundfile or numpy are absent (or the bytes
cannot be decoded), raises AudioNormaliseError so callers can fall back
to the temp-file path already used by WhisperSTT.transcribe(bytes).
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AudioNormaliseError(RuntimeError):
    """Raised when audio bytes cannot be decoded or normalised."""


def normalise_to_pcm(audio: bytes, target_sr: int = 16_000) -> Any:
    """Decode and resample *audio* bytes to a 16 kHz mono float32 numpy array.

    Args:
        audio:     Raw audio bytes in any format supported by soundfile
                   (OGG/Opus, WAV, FLAC) or libsndfile via soundfile.
        target_sr: Target sample rate in Hz. Defaults to 16 000 (Whisper).

    Returns:
        1-D float32 numpy array at *target_sr*.

    Raises:
        AudioNormaliseError: if decoding or resampling fails.
    """
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise AudioNormaliseError(
            "normalise_to_pcm requires numpy and soundfile: "
            f"pip install 'neuralcleave[voice]' ({exc})"
        ) from exc

    try:
        data, sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=False)
    except Exception as exc:
        raise AudioNormaliseError(f"soundfile could not decode audio: {exc}") from exc

    # Mix down to mono if multi-channel
    if data.ndim == 2:
        data = data.mean(axis=1)

    if sr == target_sr:
        return data

    # Lightweight linear resampling — good enough for speech, no scipy dependency
    try:
        ratio = target_sr / sr
        new_len = int(len(data) * ratio)
        indices = np.linspace(0, len(data) - 1, new_len)
        left = np.floor(indices).astype(np.int64)
        right = np.clip(left + 1, 0, len(data) - 1)
        frac = indices - left
        resampled: np.ndarray = data[left] * (1 - frac) + data[right] * frac
        return resampled.astype(np.float32)
    except Exception as exc:
        raise AudioNormaliseError(f"resampling failed: {exc}") from exc


def normalise_to_wav(audio: bytes, target_sr: int = 16_000) -> bytes:
    """Decode and resample *audio* bytes and re-encode as 16-bit PCM WAV.

    Useful when a downstream function requires a file-like WAV rather than
    a raw numpy array (e.g. pyttsx3 or a REST TTS endpoint).

    Raises:
        AudioNormaliseError: forwarded from normalise_to_pcm.
    """
    try:
        import soundfile as sf
    except ImportError as exc:
        raise AudioNormaliseError(
            "normalise_to_wav requires numpy and soundfile"
        ) from exc

    pcm = normalise_to_pcm(audio, target_sr)
    buf = io.BytesIO()
    sf.write(buf, pcm, target_sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def detect_silence(audio: bytes, threshold_rms: float = 300.0, target_sr: int = 16_000) -> bool:
    """Return True if *audio* is predominantly silence (normalised RMS below threshold).

    Uses the same int16 energy metric as :class:`~neuralcleave.voice.continuous.ContinuousVoiceListener`.
    Returns True on any decode error so callers can safely skip undecodable frames.
    """
    try:
        import numpy as np
        pcm = normalise_to_pcm(audio, target_sr)
        rms = float(np.sqrt(np.mean((pcm * 32768).astype(np.float64) ** 2)))
        return rms < threshold_rms
    except Exception:
        return True


def trim_silence(
    audio: bytes,
    threshold_rms: float = 300.0,
    frame_ms: int = 10,
    target_sr: int = 16_000,
) -> bytes:
    """Remove leading and trailing silence from *audio* bytes.

    Returns WAV bytes at *target_sr* with head/tail silence stripped.
    Falls back to returning *audio* unchanged on any decode error.

    Args:
        audio:          Raw audio bytes in any format soundfile supports.
        threshold_rms:  RMS cutoff (int16 scale, 0-32768). Frames below this
                        are treated as silence.
        frame_ms:       Frame length in milliseconds used for RMS analysis.
        target_sr:      Target sample rate; output will always be at this rate.
    """
    try:
        import io

        import numpy as np
        import soundfile as sf

        pcm = normalise_to_pcm(audio, target_sr)
        frame_size = max(1, int(target_sr * frame_ms / 1000))

        speech_mask = [
            float(np.sqrt(np.mean((pcm[i: i + frame_size] * 32768).astype(np.float64) ** 2)))
            >= threshold_rms
            for i in range(0, len(pcm), frame_size)
        ]

        if not any(speech_mask):
            return audio  # entirely silent — return original unchanged

        first = next(i for i, s in enumerate(speech_mask) if s)
        last = len(speech_mask) - 1 - next(i for i, s in enumerate(reversed(speech_mask)) if s)

        trimmed = pcm[first * frame_size: (last + 1) * frame_size]
        buf = io.BytesIO()
        sf.write(buf, trimmed, target_sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()
    except Exception:
        return audio


def load_audio_file(path: Path, target_sr: int = 16_000) -> Any:
    """Convenience wrapper: read *path* from disk and normalise to PCM array.

    Raises:
        AudioNormaliseError: if the file cannot be read or normalised.
    """
    try:
        return normalise_to_pcm(path.read_bytes(), target_sr)
    except AudioNormaliseError:
        raise
    except Exception as exc:
        raise AudioNormaliseError(f"could not load {path}: {exc}") from exc
