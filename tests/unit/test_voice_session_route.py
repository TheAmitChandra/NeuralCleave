"""Tests for GET /voice/session route."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fastapi
import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.routes import router


@pytest.fixture()
def client():
    app = fastapi.FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestVoiceSessionRoute:
    def test_available_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/session").json()
        assert data["available"] is False

    def test_available_false_when_no_tracker(self, client) -> None:
        rt = MagicMock()
        rt.get_voice_session_info.return_value = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/session").json()
        assert data["available"] is False

    def test_available_true_when_tracker_present(self, client) -> None:
        rt = MagicMock()
        rt.get_voice_session_info.return_value = {"session_id": "abc", "turn_count": 1}
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/session").json()
        assert data["available"] is True

    def test_session_id_in_response(self, client) -> None:
        rt = MagicMock()
        rt.get_voice_session_info.return_value = {"session_id": "abc-123", "turn_count": 2}
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/session").json()
        assert data["session_id"] == "abc-123"

    def test_turn_count_in_response(self, client) -> None:
        rt = MagicMock()
        rt.get_voice_session_info.return_value = {"session_id": "x", "turn_count": 5}
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/session").json()
        assert data["turn_count"] == 5

    def test_calls_get_voice_session_info(self, client) -> None:
        rt = MagicMock()
        rt.get_voice_session_info.return_value = {"session_id": "y"}
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.get("/api/v1/voice/session")
        rt.get_voice_session_info.assert_called_once()
