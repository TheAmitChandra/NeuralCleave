"""Text-to-Speech with a three-tier fallback chain.

Priority order:
    1. ElevenLabs  — cloud, highest quality (requires ELEVENLABS_API_KEY)
    2. Kokoro      — local, no API key, good quality (requires kokoro package)
    3. System TTS  — pyttsx3, zero-dependency offline fallback

Usage::

    tts = TTSEngine()
    audio_bytes = await tts.synthesize("Hello, how can I help you?")

    # Or persist to file:
    await tts.synthesize("Hello", output_path=Path("out.mp3"))

    # Custom voice cloning (ElevenLabs):
    voice_id = await tts.clone_voice("My Voice", [sample1_bytes, sample2_bytes])
    tts.use_voice(voice_id)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TTSEngine:
    """Synthesises speech using the best available provider.

    Args:
        elevenlabs_api_key: ElevenLabs API key. Falls back to env ELEVENLABS_API_KEY.
        elevenlabs_voice_id: ElevenLabs voice ID (default Rachel).
        kokoro_voice:        Kokoro voice name (e.g. "af_sarah").
        prefer_local:        If True, try Kokoro before ElevenLabs.
    """

    DEFAULT_ELEVENLABS_VOICE = "21m00Tcm4TlvDq8ikWAM"  # Rachel

    def __init__(
        self,
        *,
        elevenlabs_api_key: str | None = None,
        elevenlabs_voice_id: str | None = None,
        kokoro_voice: str = "af_sarah",
        prefer_local: bool = False,
    ) -> None:
        self._el_key = elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY", "")
        self._el_voice = elevenlabs_voice_id or self.DEFAULT_ELEVENLABS_VOICE
        self._kokoro_voice = kokoro_voice
        self._prefer_local = prefer_local

    async def synthesize(
        self,
        text: str,
        *,
        output_path: Path | None = None,
    ) -> bytes:
        """Convert text to speech. Returns raw audio bytes (MP3 or WAV).

        If output_path is given, also writes the file.
        Falls back through ElevenLabs → Kokoro → pyttsx3.
        """
        chain = (
            [self._kokoro, self._elevenlabs, self._system]
            if self._prefer_local
            else [self._elevenlabs, self._kokoro, self._system]
        )
        last_error: Exception | None = None
        for provider in chain:
            try:
                audio = await provider(text)
                if output_path:
                    output_path.write_bytes(audio)
                return audio
            except Exception as exc:
                logger.warning("tts.%s failed: %s", provider.__name__, exc)
                last_error = exc
        raise RuntimeError(f"All TTS providers failed. Last: {last_error}")

    def use_voice(self, voice_id: str) -> None:
        """Switch subsequent synthesize() calls to a specific ElevenLabs voice ID.

        Useful for switching to a voice returned by clone_voice().
        """
        self._el_voice = voice_id

    async def clone_voice(
        self,
        name: str,
        audio_samples: list[bytes],
        *,
        description: str | None = None,
    ) -> str:
        """Create a custom ElevenLabs voice from audio samples.

        Args:
            name:           Display name for the new voice.
            audio_samples:  One or more raw audio file bytes (mp3/wav/etc.)
                            used as cloning reference samples. ElevenLabs
                            recommends at least 1 minute of clean audio.
            description:    Optional voice description.

        Returns the new voice_id. Does not switch the active voice — call
        use_voice(voice_id) with the result to start using it.
        """
        if not self._el_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        if not audio_samples:
            raise ValueError("at least one audio sample is required")
        try:
            import httpx
        except ImportError:
            raise RuntimeError("pip install httpx")

        files = [
            ("files", (f"sample_{i}.mp3", sample, "audio/mpeg"))
            for i, sample in enumerate(audio_samples)
        ]
        data = {"name": name}
        if description:
            data["description"] = description

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.elevenlabs.io/v1/voices/add",
                headers={"xi-api-key": self._el_key},
                data=data,
                files=files,
                timeout=60.0,
            )
            resp.raise_for_status()
            result = resp.json()
            voice_id: str = result["voice_id"]

        logger.info("tts.clone_voice created voice_id=%s name=%s", voice_id, name)
        return voice_id

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    async def _elevenlabs(self, text: str) -> bytes:
        if not self._el_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        try:
            import httpx
        except ImportError:
            raise RuntimeError("pip install httpx")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._el_voice}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "xi-api-key": self._el_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.content

    async def _kokoro(self, text: str) -> bytes:
        try:
            import kokoro  # type: ignore[import]  # noqa: F401
        except ImportError:
            raise RuntimeError("pip install kokoro")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._kokoro_sync, text
        )

    def _kokoro_sync(self, text: str) -> bytes:
        import io

        import kokoro  # type: ignore[import]

        pipeline = kokoro.KPipeline(lang_code="a")
        samples: list[Any] = []
        for _, _, audio in pipeline(text, voice=self._kokoro_voice, speed=1.0):
            samples.append(audio)

        try:
            import numpy as np  # type: ignore[import]
            import soundfile as sf  # type: ignore[import]

            combined = np.concatenate(samples)
            buf = io.BytesIO()
            sf.write(buf, combined, 24000, format="WAV")
            return buf.getvalue()
        except ImportError:
            # Return raw float array serialised — caller gets WAV bytes
            # when numpy/soundfile unavailable, return empty as graceful fail
            raise RuntimeError("pip install numpy soundfile for Kokoro output")

    async def _system(self, text: str) -> bytes:
        try:
            import pyttsx3  # type: ignore[import]  # noqa: F401
        except ImportError:
            raise RuntimeError("pip install pyttsx3")

        return await asyncio.get_event_loop().run_in_executor(
            None, self._pyttsx3_sync, text
        )

    def _pyttsx3_sync(self, text: str) -> bytes:
        import tempfile

        import pyttsx3  # type: ignore[import]

        engine = pyttsx3.init()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = Path(f.name)
        try:
            engine.save_to_file(text, str(tmp))
            engine.runAndWait()
            return tmp.read_bytes()
        finally:
            tmp.unlink(missing_ok=True)
