"""Continuous voice listener — always-on, no wake word required.

Unlike :class:`WakeWordDetector` (which fires a callback only when a
specific keyword is spoken), :class:`ContinuousVoiceListener` transcribes
everything the user says continuously, making it the desktop equivalent of
OpenClaw's Android continuous voice mode.

How it works
^^^^^^^^^^^^
1. A ``sounddevice`` InputStream runs in a worker thread (same approach as
   :class:`WakeWordDetector`) and pushes raw PCM frames into a thread-safe
   queue.
2. An asyncio background task drains the queue, applying a simple
   energy-based Voice Activity Detector (VAD) to each frame.
3. When speech frames accumulate and then fall silent for ``silence_duration_s``
   seconds (or reach ``max_speech_duration_s``), the collected audio is sent
   to :class:`WhisperSTT` for transcription.
4. The transcription is passed to the registered callback.

Energy VAD
^^^^^^^^^^
We compute the RMS (root-mean-square) of each PCM int16 frame. Frames with
RMS >= ``silence_threshold_rms`` are treated as speech; lower frames as
silence. This requires no external VAD library — only numpy (already a
project dependency via OpenWakeWord).

Requirements
^^^^^^^^^^^^
    pip install sounddevice numpy faster-whisper

Setup example::

    from neuralcleave.voice.stt import WhisperSTT
    from neuralcleave.voice.continuous import ContinuousVoiceListener

    stt = WhisperSTT(model_size="base")
    listener = ContinuousVoiceListener(stt)

    async def on_text(text: str) -> None:
        print(f"You said: {text}")

    listener.on_transcription(on_text)
    await listener.start()
    # … keep running …
    await listener.stop()
"""

from __future__ import annotations

import asyncio
import logging
import queue
import struct
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neuralcleave.voice.stt import WhisperSTT

logger = logging.getLogger(__name__)

#: A sync or async callable that receives a transcribed text string.
TranscriptionCallback = Callable[[str], Awaitable[None] | None]


class ContinuousVoiceListener:
    """Always-on voice listener that transcribes everything the user says.

    Args:
        stt:                    :class:`~neuralcleave.voice.stt.WhisperSTT`
                                instance used for transcription.
        sample_rate:            Microphone sample rate in Hz. Must match what
                                Whisper expects (16 kHz recommended).
        chunk_ms:               Duration of each audio chunk in milliseconds.
                                Shorter chunks = lower latency VAD.
        silence_threshold_rms:  RMS energy below this value is treated as
                                silence. Raise for noisy environments; lower
                                for quiet rooms.
        silence_duration_s:     Seconds of consecutive silence after speech
                                that signals end-of-utterance.
        min_speech_duration_s:  Utterances shorter than this are discarded
                                (prevents transcribing coughs/noise bursts).
        max_speech_duration_s:  Utterances longer than this are force-ended
                                and transcribed, to avoid runaway buffering.
    """

    def __init__(
        self,
        stt: WhisperSTT,
        *,
        sample_rate: int = 16_000,
        chunk_ms: int = 30,
        silence_threshold_rms: float = 300.0,
        silence_duration_s: float = 0.8,
        min_speech_duration_s: float = 0.2,
        max_speech_duration_s: float = 30.0,
    ) -> None:
        self._stt = stt
        self._sample_rate = sample_rate
        self._chunk_ms = chunk_ms
        self._silence_threshold_rms = silence_threshold_rms
        self._silence_duration_s = silence_duration_s
        self._min_speech_duration_s = min_speech_duration_s
        self._max_speech_duration_s = max_speech_duration_s

        # Derived chunk counts
        self._chunk_samples = int(sample_rate * chunk_ms / 1000)
        self._max_silence_chunks = max(1, int(silence_duration_s * 1000 / chunk_ms))
        self._min_speech_chunks = max(1, int(min_speech_duration_s * 1000 / chunk_ms))
        self._max_speech_chunks = max(1, int(max_speech_duration_s * 1000 / chunk_ms))

        self._callback: TranscriptionCallback | None = None
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._audio_future: Any = None
        self._frame_queue: queue.Queue[bytes | None] = queue.Queue()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_transcription(self, callback: TranscriptionCallback) -> None:
        """Register the callable invoked with each transcribed utterance.

        *callback* may be a regular function or an ``async def``.  It receives
        a single ``str`` argument — the stripped transcription text.  Only one
        callback is active at a time; calling this again replaces the previous
        one.
        """
        self._callback = callback

    @property
    def is_listening(self) -> bool:
        """``True`` while the listener is actively capturing audio."""
        return self._running

    async def start(self) -> None:
        """Start continuous listening.

        Opens the microphone stream in a background executor thread and
        launches the asyncio VAD/transcription task.  Calling :meth:`start`
        while already listening is a no-op.
        """
        if self._running:
            return
        loop = asyncio.get_running_loop()
        self._running = True
        self._frame_queue = queue.Queue()
        self._task = asyncio.create_task(self._process_loop())
        self._audio_future = loop.run_in_executor(None, self._blocking_listen_loop)
        logger.info(
            "continuous_voice.started sample_rate=%d chunk_ms=%d threshold_rms=%.1f",
            self._sample_rate,
            self._chunk_ms,
            self._silence_threshold_rms,
        )

    async def stop(self) -> None:
        """Stop listening and release all resources."""
        self._running = False
        # Unblock _process_loop by sending the sentinel value
        self._frame_queue.put_nowait(None)
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._audio_future = None
        logger.info("continuous_voice.stopped")

    # ------------------------------------------------------------------
    # VAD helpers (pure, easily unit-tested)
    # ------------------------------------------------------------------

    def _compute_rms(self, frame_bytes: bytes) -> float:
        """Return the RMS energy of a PCM int16 frame.

        Uses numpy when available for speed; falls back to pure-Python
        ``struct`` unpacking so the method works even without numpy.
        """
        if not frame_bytes:
            return 0.0
        try:
            import numpy as np  # type: ignore[import]

            samples = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float64)
            rms = float(np.sqrt(np.mean(samples**2)))
            return rms
        except Exception:
            n = len(frame_bytes) // 2
            if n == 0:
                return 0.0
            values = struct.unpack_from(f"<{n}h", frame_bytes, 0)
            return (sum(v * v for v in values) / n) ** 0.5

    def _is_speech(self, frame_bytes: bytes) -> bool:
        """Return ``True`` if *frame_bytes* contains speech-level energy."""
        return self._compute_rms(frame_bytes) >= self._silence_threshold_rms

    # ------------------------------------------------------------------
    # Core async loop
    # ------------------------------------------------------------------

    async def _process_loop(self) -> None:
        """Drain the frame queue, run VAD, detect utterances, transcribe."""
        speech_frames: list[bytes] = []
        silence_count: int = 0
        loop = asyncio.get_running_loop()

        while True:
            try:
                frame: bytes | None = await loop.run_in_executor(
                    None, self._frame_queue.get, True, 0.2
                )
            except asyncio.CancelledError:
                break
            except queue.Empty:
                if not self._running:
                    break
                continue

            if frame is None:
                # Sentinel: exit immediately
                break

            if self._is_speech(frame):
                speech_frames.append(frame)
                silence_count = 0
            elif speech_frames:
                silence_count += 1
                speech_frames.append(frame)

                force_end = len(speech_frames) >= self._max_speech_chunks
                silence_end = silence_count >= self._max_silence_chunks

                if force_end or silence_end:
                    asyncio.create_task(self._flush_utterance(list(speech_frames)))
                    speech_frames = []
                    silence_count = 0

        # Flush any remaining speech on clean exit
        if speech_frames:
            await self._flush_utterance(speech_frames)

    async def _flush_utterance(self, frames: list[bytes]) -> None:
        """Transcribe *frames* and fire the callback if the result is non-empty."""
        if len(frames) < self._min_speech_chunks:
            logger.debug(
                "continuous_voice.utterance_too_short frames=%d min=%d",
                len(frames),
                self._min_speech_chunks,
            )
            return

        audio = b"".join(frames)
        try:
            text = await self._stt.transcribe(audio)
        except Exception as exc:
            logger.error("continuous_voice.transcribe_error: %s", exc)
            return

        text = text.strip()
        if not text:
            logger.debug("continuous_voice.empty_transcription skipped")
            return

        logger.info("continuous_voice.transcribed text=%r", text[:80])

        if self._callback is None:
            return
        try:
            result = self._callback(text)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.error("continuous_voice.callback_error: %s", exc)

    # ------------------------------------------------------------------
    # Audio capture (runs in executor thread)
    # ------------------------------------------------------------------

    def _audio_frame_received(
        self, indata: Any, frames: int, time_info: Any, status: Any
    ) -> None:
        """``sounddevice`` InputStream callback — pushes frames to the queue."""
        if status:
            logger.debug("continuous_voice.audio_status %s", status)
        if not self._running:
            return
        try:
            import numpy as np  # type: ignore[import]

            frame_bytes = indata[:, 0].astype(np.int16).tobytes()
        except Exception as exc:
            logger.debug("continuous_voice.frame_encode_error: %s", exc)
            return
        self._frame_queue.put_nowait(frame_bytes)

    def _blocking_listen_loop(self) -> None:
        """Open a ``sounddevice`` InputStream and block until :meth:`stop` is called."""
        try:
            import sounddevice as sd  # type: ignore[import]
        except ImportError:
            logger.error(
                "continuous_voice: pip install sounddevice numpy is required"
            )
            return

        try:
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._chunk_samples,
                callback=self._audio_frame_received,
            ):
                import time

                while self._running:
                    time.sleep(0.05)
        except Exception as exc:
            logger.error("continuous_voice.audio_loop_error: %s", exc)
