"""Tests for POST /voice/session/reset route."""

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


class TestVoiceSessionResetRoute:
    def test_reset_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/session/reset").json()
        assert data["reset"] is False

    def test_reason_present_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/session/reset").json()
        assert "reason" in data

    def test_reset_false_when_no_tracker(self, client) -> None:
        rt = MagicMock()
        rt.voice_session_reset.return_value = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/session/reset").json()
        assert data["reset"] is False

    def test_reset_true_on_success(self, client) -> None:
        rt = MagicMock()
        rt.voice_session_reset.return_value = "new-session-id"
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/session/reset").json()
        assert data["reset"] is True

    def test_session_id_in_response(self, client) -> None:
        rt = MagicMock()
        rt.voice_session_reset.return_value = "fresh-uuid"
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/session/reset").json()
        assert data["session_id"] == "fresh-uuid"

    def test_calls_voice_session_reset(self, client) -> None:
        rt = MagicMock()
        rt.voice_session_reset.return_value = "id"
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.post("/api/v1/voice/session/reset")
        rt.voice_session_reset.assert_called_once()
