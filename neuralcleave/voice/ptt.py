"""Push-to-talk recorder — bounded, VAD-free audio capture.

Unlike :class:`ContinuousVoiceListener` which runs indefinitely with VAD,
``PushToTalkRecorder`` records audio only while the caller explicitly holds
the session open.  This is the desktop equivalent of OpenClaw's PTT mode:

1. Call :meth:`start` to open the microphone and begin accumulating frames.
2. Call :meth:`stop` to close the microphone and receive the raw PCM bytes.
3. Pass those bytes to :class:`~neuralcleave.voice.stt.WhisperSTT` for
   transcription.

A ``max_duration_s`` safety cap auto-stops recording if the user forgets to
call :meth:`stop` — the internal flag is cleared and no more frames are
appended.

Requirements::

    pip install sounddevice numpy
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class PushToTalkRecorder:
    """Records audio between explicit :meth:`start` / :meth:`stop` calls.

    Args:
        sample_rate:    Microphone sample rate in Hz (must match STT expectation).
        chunk_ms:       Duration of each audio chunk in milliseconds.
        max_duration_s: Hard cap on recording length. After this many seconds
                        the recorder silently stops accepting new frames.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        chunk_ms: int = 30,
        max_duration_s: float = 30.0,
    ) -> None:
        self._sample_rate = sample_rate
        self._chunk_ms = chunk_ms
        self._max_duration_s = max_duration_s
        self._frames: list[bytes] = []
        self._recording: bool = False
        self._start_time: float | None = None
        self._audio_future: Any = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        """``True`` while a recording session is active."""
        return self._recording

    @property
    def duration_s(self) -> float:
        """Elapsed seconds since :meth:`start` was called, or 0 if not recording."""
        if self._start_time is None or not self._recording:
            return 0.0
        return time.monotonic() - self._start_time

    @property
    def frame_count(self) -> int:
        """Number of PCM frames accumulated so far."""
        return len(self._frames)

    @property
    def max_duration_s(self) -> float:
        """Hard cap on recording length in seconds."""
        return self._max_duration_s

    @property
    def sample_rate(self) -> int:
        """Microphone sample rate used for this recorder."""
        return self._sample_rate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Open the microphone and start accumulating frames.

        Calling :meth:`start` while already recording is a no-op.
        """
        if self._recording:
            return
        self._frames = []
        self._recording = True
        self._start_time = time.monotonic()
        loop = asyncio.get_running_loop()
        self._audio_future = loop.run_in_executor(None, self._blocking_record_loop)
        logger.info(
            "ptt.started sample_rate=%d chunk_ms=%d max_duration_s=%.1f",
            self._sample_rate, self._chunk_ms, self._max_duration_s,
        )

    async def stop(self) -> bytes:
        """Stop recording and return all accumulated PCM frames as a single bytes object.

        Calling :meth:`stop` while not recording returns an empty bytes object.
        """
        if not self._recording:
            return b""

        self._recording = False
        if self._audio_future is not None:
            try:
                await self._audio_future
            except Exception as exc:
                logger.debug("ptt.stop audio_future error: %s", exc)
            self._audio_future = None

        audio = b"".join(self._frames)
        self._start_time = None
        logger.info("ptt.stopped frame_count=%d bytes=%d", len(self._frames), len(audio))
        return audio

    # ------------------------------------------------------------------
    # Audio capture (runs in executor thread)
    # ------------------------------------------------------------------

    def _audio_frame_received(
        self, indata: Any, frames: int, time_info: Any, status: Any
    ) -> None:
        """``sounddevice`` callback — appends frames while under the time cap."""
        if not self._recording:
            return
        if self._start_time is not None:
            elapsed = time.monotonic() - self._start_time
            if elapsed >= self._max_duration_s:
                logger.info("ptt.max_duration_reached duration_s=%.1f", elapsed)
                self._recording = False
                return
        try:
            import numpy as np  # type: ignore[import]
            frame_bytes = indata[:, 0].astype(np.int16).tobytes()
            self._frames.append(frame_bytes)
        except Exception as exc:
            logger.debug("ptt.frame_encode_error: %s", exc)

    def _blocking_record_loop(self) -> None:
        """Open a ``sounddevice`` InputStream and block until :meth:`stop` clears the flag."""
        try:
            import sounddevice as sd  # type: ignore[import]
        except ImportError:
            logger.error("ptt: pip install sounddevice numpy is required")
            return

        chunk_samples = int(self._sample_rate * self._chunk_ms / 1000)
        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=chunk_samples,
                callback=self._audio_frame_received,
            ):
                while self._recording:
                    time.sleep(0.05)
        except Exception as exc:
            logger.error("ptt.audio_loop_error: %s", exc)
