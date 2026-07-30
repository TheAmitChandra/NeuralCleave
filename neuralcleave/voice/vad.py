"""Voice Activity Detection — pluggable VAD engine for the audio pipeline.

Provides :class:`VoiceActivityDetector`, a thin wrapper around one of several
VAD backends. Currently ships with an energy-based backend (no extra deps) and
a stub hook for ``webrtcvad`` (a C extension available via pip).

The energy backend matches the ad-hoc ``_compute_rms`` / ``_is_speech`` logic
previously inlined in :class:`~neuralcleave.voice.continuous.ContinuousVoiceListener`.
Extracting it here lets callers share one instance, makes thresholds configurable
at the gateway-config level, and exposes simple frame counters for metrics.

Usage::

    from neuralcleave.voice.vad import VoiceActivityDetector

    vad = VoiceActivityDetector(threshold_rms=300.0, sample_rate=16_000)
    is_speech = vad.is_speech(pcm_frame_bytes)
    print(vad.speech_frames, vad.silence_frames)
"""

from __future__ import annotations

import logging
import struct

logger = logging.getLogger(__name__)

#: Recognised backend identifiers.
BACKENDS = frozenset({"energy", "webrtcvad"})


class VADError(RuntimeError):
    """Raised when the VAD backend cannot be initialised."""


class VoiceActivityDetector:
    """Energy or WebRTC-VAD based voice activity detector.

    Args:
        backend:        ``"energy"`` (default) or ``"webrtcvad"``.
                        ``"energy"`` requires only numpy (optional, falls back
                        to pure-Python struct); ``"webrtcvad"`` requires the
                        ``webrtcvad`` package.
        threshold_rms:  Energy backend only — int16-scale RMS below which a
                        frame is treated as silence.  Typical values: 100–500.
        sample_rate:    Sample rate of PCM int16 frames in Hz.  Must be one of
                        8000, 16000, 32000, or 48000 for ``webrtcvad``; any
                        positive int for ``"energy"``.
        aggressiveness: WebRTC-VAD aggressiveness 0–3 (0 = least aggressive).
                        Ignored by the energy backend.
    """

    def __init__(
        self,
        *,
        backend: str = "energy",
        threshold_rms: float = 300.0,
        sample_rate: int = 16_000,
        aggressiveness: int = 2,
    ) -> None:
        if backend not in BACKENDS:
            raise VADError(f"Unknown VAD backend {backend!r}. Choose from {sorted(BACKENDS)}")
        self._backend = backend
        self._threshold_rms = threshold_rms
        self._sample_rate = sample_rate
        self._aggressiveness = aggressiveness
        self._webrtcvad: object | None = None

        self._speech_frames: int = 0
        self._silence_frames: int = 0

        if backend == "webrtcvad":
            self._init_webrtcvad()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def backend(self) -> str:
        """Active backend identifier."""
        return self._backend

    @property
    def threshold_rms(self) -> float:
        """Energy-VAD RMS threshold (int16 scale)."""
        return self._threshold_rms

    @threshold_rms.setter
    def threshold_rms(self, value: float) -> None:
        self._threshold_rms = float(value)

    @property
    def sample_rate(self) -> int:
        """Sample rate of PCM frames this instance expects."""
        return self._sample_rate

    @property
    def speech_frames(self) -> int:
        """Cumulative count of frames classified as speech."""
        return self._speech_frames

    @property
    def silence_frames(self) -> int:
        """Cumulative count of frames classified as silence."""
        return self._silence_frames

    def reset_counters(self) -> None:
        """Reset :attr:`speech_frames` and :attr:`silence_frames` to zero."""
        self._speech_frames = 0
        self._silence_frames = 0

    def is_speech(self, frame: bytes) -> bool:
        """Return ``True`` if *frame* contains speech-level audio.

        The result updates :attr:`speech_frames` / :attr:`silence_frames`.

        Args:
            frame: Raw PCM int16 bytes at :attr:`sample_rate`.
        """
        if not frame:
            self._silence_frames += 1
            return False
        if self._backend == "webrtcvad":
            result = self._webrtcvad_is_speech(frame)
        else:
            result = self._energy_is_speech(frame)
        if result:
            self._speech_frames += 1
        else:
            self._silence_frames += 1
        return result

    def compute_rms(self, frame: bytes) -> float:
        """Compute int16-scale RMS energy of *frame* without updating counters."""
        return _compute_rms(frame)

    # ------------------------------------------------------------------
    # Energy backend
    # ------------------------------------------------------------------

    def _energy_is_speech(self, frame: bytes) -> bool:
        return _compute_rms(frame) >= self._threshold_rms

    # ------------------------------------------------------------------
    # WebRTC-VAD backend
    # ------------------------------------------------------------------

    def _init_webrtcvad(self) -> None:
        try:
            import webrtcvad  # type: ignore[import]

            vad = webrtcvad.Vad(self._aggressiveness)
            self._webrtcvad = vad
            logger.info("vad.webrtcvad_initialised aggressiveness=%d", self._aggressiveness)
        except ImportError as exc:
            raise VADError(
                "webrtcvad backend requires the 'webrtcvad' package: "
                "pip install webrtcvad"
            ) from exc

    def _webrtcvad_is_speech(self, frame: bytes) -> bool:
        if self._webrtcvad is None:
            return self._energy_is_speech(frame)
        try:
            import webrtcvad  # noqa: F401  # ensures it's available

            return bool(self._webrtcvad.is_speech(frame, self._sample_rate))  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("vad.webrtcvad_error falling back to energy: %s", exc)
            return self._energy_is_speech(frame)


# ---------------------------------------------------------------------------
# Module-level helpers (pure, no state)
# ---------------------------------------------------------------------------


def _compute_rms(frame: bytes) -> float:
    """Return int16-scale RMS energy of *frame* (no numpy required)."""
    if not frame:
        return 0.0
    try:
        import numpy as np

        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float64)
        return float(np.sqrt(np.mean(samples**2)))
    except Exception:
        n = len(frame) // 2
        if n == 0:
            return 0.0
        values = struct.unpack_from(f"<{n}h", frame, 0)
        return (sum(v * v for v in values) / n) ** 0.5
