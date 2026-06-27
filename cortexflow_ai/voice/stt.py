"""Speech-to-Text using faster-whisper (local, no API key needed).

Supports transcription from file bytes or Path, plus streaming chunks.
Runs on CPU by default; set device="cuda" for GPU acceleration.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class WhisperSTT:
    """Local STT using faster-whisper.

    Requires ``pip install faster-whisper``.

    Args:
        model_size: Whisper model size. Smaller = faster, lower quality.
                    Options: tiny | base | small | medium | large-v3
        device:     "cpu" or "cuda" (requires CUDA + GPU).
        language:   ISO language code ("en", "de", etc.) or None for auto-detect.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        language: str | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.language = language
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore[import]
            except ImportError:
                raise RuntimeError("pip install faster-whisper")
            self._model = WhisperModel(self.model_size, device=self.device, compute_type="int8")
            logger.info("WhisperSTT loaded model=%s device=%s", self.model_size, self.device)
        return self._model

    async def transcribe(self, audio: bytes | Path) -> str:
        """Transcribe audio bytes or a file path to text.

        For bytes input, writes to a temporary file then reads it.
        This is synchronous under the hood — for a busy gateway, run in
        a thread pool executor to avoid blocking the event loop.
        """
        import asyncio

        return await asyncio.get_event_loop().run_in_executor(
            None, self._transcribe_sync, audio
        )

    def _transcribe_sync(self, audio: bytes | Path) -> str:
        model = self._load()
        if isinstance(audio, bytes):
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(audio)
                tmp = Path(f.name)
            try:
                return self._run(model, tmp)
            finally:
                tmp.unlink(missing_ok=True)
        return self._run(model, audio)

    def _run(self, model: Any, path: Path) -> str:
        segments, _info = model.transcribe(
            str(path),
            language=self.language,
            beam_size=5,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    async def transcribe_stream(
        self, chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[str]:
        """Consume audio chunks and yield partial transcripts.

        Buffers every N chunks into a temp file, transcribes, and yields.
        For real-time use, buffer_size controls the latency/accuracy tradeoff.
        """

        buffer = b""
        buffer_size = 32_768  # ~2 seconds of 16kHz mono

        async for chunk in chunks:
            buffer += chunk
            if len(buffer) >= buffer_size:
                text = await self.transcribe(buffer)
                buffer = b""
                if text:
                    yield text

        if buffer:
            text = await self.transcribe(buffer)
            if text:
                yield text
