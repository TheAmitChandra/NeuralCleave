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
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from neuralcleave.voice.audio import AudioChunkBuffer
from neuralcleave.voice.vad import VoiceActivityDetector

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
        vad_aggressiveness: int = 2,
        vad_backend: str = "energy",
        device: str | int | None = None,
    ) -> None:
        self._stt = stt
        self._sample_rate = sample_rate
        self._chunk_ms = chunk_ms
        self._device = device
        self._silence_threshold_rms = silence_threshold_rms
        self._silence_duration_s = silence_duration_s
        self._min_speech_duration_s = min_speech_duration_s
        self._max_speech_duration_s = max_speech_duration_s

        # Derived chunk counts
        self._chunk_samples = int(sample_rate * chunk_ms / 1000)
        self._max_silence_chunks = max(1, int(silence_duration_s * 1000 / chunk_ms))
        self._min_speech_chunks = max(1, int(min_speech_duration_s * 1000 / chunk_ms))
        self._max_speech_chunks = max(1, int(max_speech_duration_s * 1000 / chunk_ms))

        self._vad = VoiceActivityDetector(
            backend=vad_backend,
            threshold_rms=silence_threshold_rms,
            sample_rate=sample_rate,
            aggressiveness=vad_aggressiveness,
        )
        self._chunk_buffer = AudioChunkBuffer(
            self._vad,
            chunk_ms=chunk_ms,
            sample_rate=sample_rate,
            silence_duration_s=silence_duration_s,
            min_speech_duration_s=min_speech_duration_s,
            max_speech_duration_s=max_speech_duration_s,
        )
        self._callback: TranscriptionCallback | None = None
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._audio_future: Any = None
        self._frame_queue: queue.Queue[bytes | None] = queue.Queue()
        self._utterance_count: int = 0
        self._last_transcript: str = ""

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

    @property
    def utterance_count(self) -> int:
        """Number of non-empty utterances successfully transcribed since start."""
        return self._utterance_count

    @property
    def last_transcript(self) -> str:
        """The most recent transcribed text, or an empty string if none yet."""
        return self._last_transcript

    def set_silence_threshold(self, rms: float) -> None:
        """Update the VAD RMS silence threshold on the live instance."""
        self._silence_threshold_rms = float(rms)
        self._vad.threshold_rms = float(rms)

    def set_device(self, device: str | int | None) -> None:
        """Update the input device used for the next :meth:`start` call.

        The change takes effect the next time the listener is (re)started;
        updating while already listening requires calling :meth:`stop` first.
        """
        self._device = device

    def set_silence_duration(self, duration_s: float) -> None:
        """Update silence duration and recompute chunk counts on the live instance."""
        self._silence_duration_s = float(duration_s)
        self._max_silence_chunks = max(1, int(duration_s * 1000 / self._chunk_ms))
        self._chunk_buffer._max_silence_chunks = self._max_silence_chunks

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
    # VAD helpers — delegate to shared VoiceActivityDetector
    # ------------------------------------------------------------------

    @property
    def vad(self) -> VoiceActivityDetector:
        """The :class:`~neuralcleave.voice.vad.VoiceActivityDetector` used internally."""
        return self._vad

    def _compute_rms(self, frame_bytes: bytes) -> float:
        """Return the RMS energy of *frame_bytes* (delegates to VAD module)."""
        return self._vad.compute_rms(frame_bytes)

    def _is_speech(self, frame_bytes: bytes) -> bool:
        """Return ``True`` if *frame_bytes* contains speech-level energy."""
        return self._vad.is_speech(frame_bytes)

    # ------------------------------------------------------------------
    # Core async loop
    # ------------------------------------------------------------------

    async def _process_loop(self) -> None:
        """Drain the frame queue through AudioChunkBuffer, transcribe completed utterances."""
        loop = asyncio.get_running_loop()
        self._chunk_buffer.reset()

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
                break

            utterance = self._chunk_buffer.push(frame)
            if utterance is not None:
                asyncio.create_task(self._flush_utterance_bytes(utterance))

        # Flush any remaining speech on clean exit
        remaining = self._chunk_buffer.flush()
        if remaining is not None:
            await self._flush_utterance_bytes(remaining)

    async def _flush_utterance_bytes(self, audio: bytes) -> None:
        """Transcribe *audio* bytes and fire the callback if the result is non-empty."""
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
        self._utterance_count += 1
        self._last_transcript = text

        try:
            from neuralcleave.observability.metrics import REGISTRY
            REGISTRY.inc("vad_utterances_total")
            REGISTRY.inc("vad_speech_frames_total", self._vad.speech_frames)
            REGISTRY.inc("vad_silence_frames_total", self._vad.silence_frames)
            self._vad.reset_counters()
        except Exception:
            pass

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
                device=self._device,
            ):
                import time

                while self._running:
                    time.sleep(0.05)
        except Exception as exc:
            logger.error("continuous_voice.audio_loop_error: %s", exc)
