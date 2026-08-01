"""Tests synthesize_stream() fallback path yields full synthesis as single chunk."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


class TestSynthesizeStreamFallback:
    @pytest.mark.asyncio
    async def test_fallback_yields_one_chunk(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="")
        audio = b"\xff\xfb\x90\x00" * 100

        with patch.object(tts, "synthesize", AsyncMock(return_value=audio)):
            collected = [c async for c in tts.synthesize_stream("hello")]

        assert len(collected) == 1
        assert collected[0] == audio

    @pytest.mark.asyncio
    async def test_fallback_yields_nothing_on_none(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="")

        with patch.object(tts, "synthesize", AsyncMock(return_value=None)):
            collected = [c async for c in tts.synthesize_stream("empty")]

        assert collected == []

    @pytest.mark.asyncio
    async def test_fallback_text_passed_to_synthesize(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="")
        synth = AsyncMock(return_value=b"audio")

        with patch.object(tts, "synthesize", synth):
            _ = [c async for c in tts.synthesize_stream("speak this")]

        synth.assert_awaited_once_with("speak this")
