"""Tests for GET /voice/ptt/status route."""

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


class TestPttStatusRoute:
    def test_available_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/ptt/status").json()
        assert data["available"] is False

    def test_is_recording_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/ptt/status").json()
        assert data["is_recording"] is False

    def test_duration_s_zero_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/ptt/status").json()
        assert data["duration_s"] == 0.0

    def test_available_true_when_ptt_configured(self, client) -> None:
        rt = MagicMock()
        rt._ptt = MagicMock(is_recording=False, duration_s=0.0)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/ptt/status").json()
        assert data["available"] is True

    def test_is_recording_true_when_ptt_active(self, client) -> None:
        rt = MagicMock()
        rt._ptt = MagicMock(is_recording=True, duration_s=2.5)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/ptt/status").json()
        assert data["is_recording"] is True

    def test_duration_s_from_ptt(self, client) -> None:
        rt = MagicMock()
        rt._ptt = MagicMock(is_recording=True, duration_s=3.7)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/ptt/status").json()
        assert data["duration_s"] == pytest.approx(3.7, rel=1e-3)

    def test_available_false_when_ptt_none_on_runtime(self, client) -> None:
        rt = MagicMock()
        rt._ptt = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/ptt/status").json()
        assert data["available"] is False
