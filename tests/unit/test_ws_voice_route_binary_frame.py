"""Tests that /ws/voice forwards binary frames to _handle_audio_frame_stream."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuralcleave.gateway.websocket import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestVoiceWsRouteBinaryFrame:
    def test_binary_frame_triggers_handler(self) -> None:
        client = _make_client()
        rt = MagicMock()
        rt._stt = None

        manager = MagicMock()
        manager.add = MagicMock()
        manager.remove = MagicMock()

        handler_calls: list[bytes] = []

        async def _fake_handler(session, data):
            handler_calls.append(data)

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.gateway.websocket.get_manager", return_value=manager), \
             patch("neuralcleave.gateway.websocket._handle_audio_frame_stream", _fake_handler):
            with client.websocket_connect("/ws/voice") as ws:
                ws.send_bytes(b"audio_frame")

        assert len(handler_calls) >= 1
        assert handler_calls[0] == b"audio_frame"
