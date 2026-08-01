"""Tests that /ws/voice WebSocket endpoint accepts connections."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuralcleave.gateway.websocket import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestVoiceWsRouteAccepts:
    def test_websocket_route_exists(self) -> None:
        client = _make_client()
        rt = MagicMock()
        rt._stt = None

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.gateway.websocket.get_manager", return_value=MagicMock()):
            with client.websocket_connect("/ws/voice") as ws:
                ws.close()

    def test_connection_accepted_with_runtime(self) -> None:
        client = _make_client()
        rt = MagicMock()
        rt._stt = None

        manager = MagicMock()
        manager.add = MagicMock()
        manager.remove = MagicMock()

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.gateway.websocket.get_manager", return_value=manager):
            with client.websocket_connect("/ws/voice"):
                pass  # connection accepted without error

        manager.add.assert_called_once()
