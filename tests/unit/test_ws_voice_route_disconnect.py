"""Tests that /ws/voice handles client disconnect gracefully."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuralcleave.gateway.websocket import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestVoiceWsRouteDisconnect:
    def test_disconnect_removes_session(self) -> None:
        client = _make_client()
        rt = MagicMock()
        rt._stt = None

        manager = MagicMock()
        manager.add = MagicMock()
        manager.remove = MagicMock()

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.gateway.websocket.get_manager", return_value=manager):
            with client.websocket_connect("/ws/voice"):
                pass  # context exit = disconnect

        manager.remove.assert_called_once()

    def test_disconnect_does_not_raise(self) -> None:
        client = _make_client()
        rt = MagicMock()
        rt._stt = None

        manager = MagicMock()
        manager.add = MagicMock()
        manager.remove = MagicMock()

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=rt), \
             patch("neuralcleave.gateway.websocket.get_manager", return_value=manager):
            with client.websocket_connect("/ws/voice") as ws:
                ws.close()  # explicit close — must not raise
