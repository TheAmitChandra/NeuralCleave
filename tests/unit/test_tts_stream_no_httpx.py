"""Tests synthesize_stream() fallback when httpx is not installed."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


class TestSynthesizeStreamNoHttpx:
    @pytest.mark.asyncio
    async def test_no_httpx_falls_back_to_synthesize(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="test-key")
        audio = b"fallback"

        saved = sys.modules.get("httpx")
        sys.modules["httpx"] = None  # type: ignore[assignment]
        try:
            with patch.object(tts, "synthesize", AsyncMock(return_value=audio)):
                collected = [c async for c in tts.synthesize_stream("hi")]
        finally:
            if saved is not None:
                sys.modules["httpx"] = saved
            else:
                sys.modules.pop("httpx", None)

        assert collected == [audio]
