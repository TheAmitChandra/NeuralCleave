"""Wake word detection using OpenWakeWord (open-source, cross-platform).

OpenWakeWord (https://github.com/dscripka/openWakeWord) runs locally with no
API key. Supports custom wake word models trained via the project's tools.

Unlike OpenClaw's macOS-only wake word, this works on Windows, macOS, and Linux.

Setup:
    pip install openwakeword>=0.5.0 sounddevice numpy

    Pre-trained models are downloaded automatically on first use.
    To use a custom model, point ``model_path`` to your .tflite file.

Usage::

    detector = WakeWordDetector(
        model="hey_jarvis",     # built-in model name
        threshold=0.5,
        on_wake=my_callback,    # called when wake word detected
    )
    await detector.start()
    # … keep running …
    await detector.stop()

Supported built-in models (downloaded automatically):
    "hey_jarvis", "hey_mycroft", "hey_rhasspy", "ok_nabu"

Custom model::

    detector = WakeWordDetector(
        model_path="/path/to/my_wake_word.tflite",
        on_wake=my_callback,
    )
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

WakeCallback = Callable[[], Awaitable[None] | None]

# Audio parameters matching OpenWakeWord's expected input
_SAMPLE_RATE = 16_000   # Hz
_CHUNK_SIZE = 1_280     # ~80ms at 16kHz — openwakeword default
_CHANNELS = 1
_DTYPE = "int16"


class WakeWordDetector:
    """Detect a configurable wake word from the microphone in real time.

    Args:
        model:       Name of a built-in OpenWakeWord model (e.g. "hey_jarvis").
        model_path:  Path to a custom .tflite model file. Takes precedence over *model*.
        threshold:   Activation score threshold (0–1). Lower = more sensitive.
        on_wake:     Async or sync callback invoked on detection.
        cooldown:    Minimum seconds between consecutive detections (debounce).
    """

    def __init__(
        self,
        *,
        model: str = "hey_jarvis",
        model_path: str | None = None,
        threshold: float = 0.5,
        on_wake: WakeCallback | None = None,
        cooldown: float = 3.0,
    ) -> None:
        self._model_name = model
        self._model_path = model_path
        self._threshold = max(0.0, min(1.0, threshold))
        self._on_wake = on_wake
        self._cooldown = cooldown
        self._oww: Any | None = None        # OpenWakeWord model instance
        self._stream: Any | None = None     # sounddevice InputStream
        self._running = False
        self._last_detection = 0.0          # epoch timestamp

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise the model and start listening on the default microphone."""
        self._oww = await self._load_model()
        self._running = True
        loop = asyncio.get_running_loop()
        # Run the blocking audio loop in a thread to keep the event loop free
        asyncio.create_task(
            loop.run_in_executor(None, self._blocking_audio_loop)
        )
        logger.info(
            "wake_word.started model=%s threshold=%.2f",
            self._model_path or self._model_name,
            self._threshold,
        )

    async def stop(self) -> None:
        """Stop listening and release audio resources."""
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._oww = None
        logger.info("wake_word.stopped")

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    async def _load_model(self) -> Any:
        try:
            import openwakeword  # type: ignore[import]
            from openwakeword.model import Model  # type: ignore[import]
        except ImportError:
            raise RuntimeError(
                "pip install openwakeword>=0.5.0 sounddevice numpy"
            )

        loop = asyncio.get_running_loop()

        def _load() -> Any:
            if self._model_path:
                return Model(wakeword_models=[self._model_path])
            # Named model — openwakeword downloads it on first use
            return Model(wakeword_models=[self._model_name])

        try:
            oww = await loop.run_in_executor(None, _load)
            logger.debug(
                "wake_word.model_loaded name=%s",
                self._model_path or self._model_name,
            )
            return oww
        except Exception as exc:
            raise RuntimeError(f"Wake word model load failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Audio loop (runs in thread executor — not on the event loop)
    # ------------------------------------------------------------------

    def _blocking_audio_loop(self) -> None:
        try:
            import numpy as np  # type: ignore[import]
            import sounddevice as sd  # type: ignore[import]
        except ImportError:
            logger.error("wake_word: pip install sounddevice numpy")
            return

        def _audio_callback(
            indata: Any, frames: int, time_info: Any, status: Any
        ) -> None:
            if status:
                logger.debug("wake_word.audio_status %s", status)
            if not self._oww:
                return
            audio = indata[:, 0].astype("int16")
            scores = self._oww.predict(audio)
            self._check_scores(scores)

        try:
            self._stream = sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype=_DTYPE,
                blocksize=_CHUNK_SIZE,
                callback=_audio_callback,
            )
            with self._stream:
                while self._running:
                    import time
                    time.sleep(0.1)
        except Exception as exc:
            logger.error("wake_word.audio_loop error: %s", exc)

    def _check_scores(self, scores: dict[str, float]) -> None:
        import time

        now = time.monotonic()
        if now - self._last_detection < self._cooldown:
            return

        for word, score in scores.items():
            if score >= self._threshold:
                self._last_detection = now
                logger.info(
                    "wake_word.detected word=%s score=%.3f", word, score
                )
                if self._on_wake:
                    # Schedule the callback on the running event loop
                    try:
                        loop = asyncio.get_event_loop()
                        result = self._on_wake()
                        if asyncio.iscoroutine(result):
                            asyncio.run_coroutine_threadsafe(result, loop)
                    except RuntimeError:
                        pass
                break  # only fire once per chunk even if multiple words detected
