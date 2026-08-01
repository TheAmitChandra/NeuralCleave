"""Tests that _elevenlabs_stream() requests use eleven_turbo_v2_5 model."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


class TestElevenLabsStreamModelId:
    @pytest.mark.asyncio
    async def test_uses_turbo_model(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="key")
        captured_json: list[dict] = []

        async def fake_aiter_bytes(_size=4096):
            yield b"mp3"

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.aiter_bytes = fake_aiter_bytes

        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=response)
        stream_cm.__aexit__ = AsyncMock(return_value=False)

        client = MagicMock()

        def _cap(method, url, *, json=None, **kw):
            if json:
                captured_json.append(json)
            return stream_cm

        client.stream = _cap
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client):
            _ = [c async for c in tts.synthesize_stream("hello")]

        assert captured_json
        assert captured_json[0]["model_id"] == "eleven_turbo_v2_5"
