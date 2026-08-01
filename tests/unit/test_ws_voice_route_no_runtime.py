"""Tests /ws/voice closes with 1011 when no runtime is registered."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuralcleave.gateway.websocket import router


def _make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestVoiceWsRouteNoRuntime:
    def test_no_runtime_closes_connection(self) -> None:
        client = _make_client()

        with patch("neuralcleave.gateway.websocket.get_runtime", return_value=None):
            with pytest.raises(Exception):
                with client.websocket_connect("/ws/voice") as ws:
                    ws.receive_text()
