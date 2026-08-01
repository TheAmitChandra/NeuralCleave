"""Tests _handle_audio_frame_stream() with no registered runtime."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.gateway.websocket import Session, _handle_audio_frame_stream


def _make_session() -> Session:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return Session(websocket=ws)


class TestStreamHandlerNoRuntime:
    @pytest.mark.asyncio
    async def test_no_runtime_returns_silently(self) -> None:
        session = _make_session()
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=None):
            await _handle_audio_frame_stream(session, b"audio")
        session.websocket.send_bytes.assert_not_awaited()
        session.websocket.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_runtime_does_not_raise(self) -> None:
        session = _make_session()
        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=None):
            await _handle_audio_frame_stream(session, b"data")  # must not raise
