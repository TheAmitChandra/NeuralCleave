"""Tests that _elevenlabs_stream() calls the /stream endpoint URL."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


class TestElevenLabsStreamEndpoint:
    @pytest.mark.asyncio
    async def test_url_contains_stream_path(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="k", elevenlabs_voice_id="voice123")
        captured_url: list[str] = []

        async def fake_aiter_bytes(_size=4096):
            yield b"audio"

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.aiter_bytes = fake_aiter_bytes

        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=response)
        stream_cm.__aexit__ = AsyncMock(return_value=False)

        client = MagicMock()

        def _capture_stream(method, url, **kw):
            captured_url.append(url)
            return stream_cm

        client.stream = _capture_stream
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client):
            _ = [c async for c in tts.synthesize_stream("hello")]

        assert len(captured_url) == 1
        assert "/stream" in captured_url[0]
        assert "voice123" in captured_url[0]

    @pytest.mark.asyncio
    async def test_url_uses_configured_voice_id(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="k", elevenlabs_voice_id="myVoiceID")
        captured: list[str] = []

        async def fake_aiter_bytes(_size=4096):
            yield b"data"

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.aiter_bytes = fake_aiter_bytes

        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=response)
        stream_cm.__aexit__ = AsyncMock(return_value=False)

        client = MagicMock()

        def _cap(method, url, **kw):
            captured.append(url)
            return stream_cm

        client.stream = _cap
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client):
            _ = [c async for c in tts.synthesize_stream("test")]

        assert "myVoiceID" in captured[0]
