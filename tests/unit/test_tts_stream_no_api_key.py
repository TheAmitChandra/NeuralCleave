"""Tests synthesize_stream() fallback when ElevenLabs API key is missing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


class TestSynthesizeStreamNoApiKey:
    @pytest.mark.asyncio
    async def test_no_key_falls_back_to_synthesize(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="")
        audio_bytes = b"fallback_audio"

        with patch.object(tts, "synthesize", AsyncMock(return_value=audio_bytes)):
            collected = [c async for c in tts.synthesize_stream("hello")]

        assert collected == [audio_bytes]

    @pytest.mark.asyncio
    async def test_no_key_synthesize_called_once(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="")
        synth = AsyncMock(return_value=b"audio")

        with patch.object(tts, "synthesize", synth):
            _ = [c async for c in tts.synthesize_stream("text")]

        synth.assert_awaited_once_with("text")

    @pytest.mark.asyncio
    async def test_no_key_synthesize_none_yields_nothing(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="")

        with patch.object(tts, "synthesize", AsyncMock(return_value=None)):
            collected = [c async for c in tts.synthesize_stream("empty")]

        assert collected == []
