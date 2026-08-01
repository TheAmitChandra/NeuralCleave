"""Tests that synthesize_stream() yields audio chunks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.voice.tts import TTSEngine


def _mock_httpx_stream(chunks: list[bytes]) -> MagicMock:
    cm = MagicMock()

    async def _aiter_bytes(_size=4096):
        for chunk in chunks:
            yield chunk

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.aiter_bytes = _aiter_bytes

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    client = MagicMock()
    client.stream = MagicMock(return_value=stream_cm)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    cm.return_value = client
    return cm


class TestSynthesizeStreamYieldsChunks:
    @pytest.mark.asyncio
    async def test_yields_multiple_chunks(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="test-key")
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        with patch("httpx.AsyncClient", _mock_httpx_stream(chunks)):
            collected = [c async for c in tts.synthesize_stream("hello")]

        assert collected == chunks

    @pytest.mark.asyncio
    async def test_filters_empty_chunks(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="test-key")
        chunks = [b"audio", b"", b"more"]

        with patch("httpx.AsyncClient", _mock_httpx_stream(chunks)):
            collected = [c async for c in tts.synthesize_stream("hello")]

        assert collected == [b"audio", b"more"]

    @pytest.mark.asyncio
    async def test_yields_bytes_type(self) -> None:
        tts = TTSEngine(elevenlabs_api_key="test-key")

        with patch("httpx.AsyncClient", _mock_httpx_stream([b"audio_data"])):
            collected = [c async for c in tts.synthesize_stream("test")]

        assert all(isinstance(c, bytes) for c in collected)
