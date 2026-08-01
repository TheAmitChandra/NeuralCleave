"""Tests synthesize_stream() fallback on HTTP errors from ElevenLabs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


def _mock_httpx_error(status_code: int = 429) -> MagicMock:
    import httpx

    response = MagicMock()
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            f"{status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    )

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    client = MagicMock()
    client.stream = MagicMock(return_value=stream_cm)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    cm = MagicMock(return_value=client)
    return cm


class TestSynthesizeStreamHttpError:
    @pytest.mark.asyncio
    async def test_http_error_falls_back_to_synthesize(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="test-key")
        audio = b"fallback_audio"

        with patch("httpx.AsyncClient", _mock_httpx_error(429)):
            with patch.object(tts, "synthesize", AsyncMock(return_value=audio)):
                collected = [c async for c in tts.synthesize_stream("rate limited")]

        assert collected == [audio]
