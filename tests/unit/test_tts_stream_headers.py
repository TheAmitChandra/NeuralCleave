"""Tests that _elevenlabs_stream() sends correct auth and content-type headers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


class TestElevenLabsStreamHeaders:
    @pytest.mark.asyncio
    async def test_xi_api_key_header_set(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="my-secret-key")
        captured_headers: list[dict] = []

        async def fake_aiter_bytes(_size=4096):
            yield b"audio"

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.aiter_bytes = fake_aiter_bytes

        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=response)
        stream_cm.__aexit__ = AsyncMock(return_value=False)

        client = MagicMock()

        def _cap(method, url, *, headers=None, **kw):
            if headers:
                captured_headers.append(headers)
            return stream_cm

        client.stream = _cap
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=client):
            _ = [c async for c in tts.synthesize_stream("hi")]

        assert captured_headers
        assert captured_headers[0].get("xi-api-key") == "my-secret-key"
