"""Tests for POST /voice/ptt/stop route."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import fastapi
import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.routes import router


@pytest.fixture()
def client():
    app = fastapi.FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestPttStopRoute:
    def test_returns_stopped_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/ptt/stop").json()
        assert data["stopped"] is False

    def test_returns_empty_response_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/ptt/stop").json()
        assert data["response"] == ""

    def test_returns_stopped_true_on_success(self, client) -> None:
        rt = MagicMock()
        rt.ptt_stop_and_respond = AsyncMock(return_value="hello back")
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/ptt/stop").json()
        assert data["stopped"] is True

    def test_response_contains_assistant_reply(self, client) -> None:
        rt = MagicMock()
        rt.ptt_stop_and_respond = AsyncMock(return_value="the answer")
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/ptt/stop").json()
        assert data["response"] == "the answer"

    def test_calls_ptt_stop_and_respond(self, client) -> None:
        rt = MagicMock()
        rt.ptt_stop_and_respond = AsyncMock(return_value="")
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.post("/api/v1/voice/ptt/stop")
        rt.ptt_stop_and_respond.assert_called_once()

    def test_empty_response_when_nothing_transcribed(self, client) -> None:
        rt = MagicMock()
        rt.ptt_stop_and_respond = AsyncMock(return_value="")
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/ptt/stop").json()
        assert data["response"] == ""
        assert data["stopped"] is True
