"""Tests for POST /voice/calibrate route."""

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


class TestVoiceCalibrateRoute:
    def test_calibrated_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/calibrate", json={}).json()
        assert data["calibrated"] is False

    def test_reason_present_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/calibrate", json={}).json()
        assert "reason" in data

    def test_calibrated_true_on_success(self, client) -> None:
        rt = MagicMock()
        rt.voice_calibrate = AsyncMock(return_value=250.0)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/calibrate", json={}).json()
        assert data["calibrated"] is True

    def test_measured_rms_returned(self, client) -> None:
        rt = MagicMock()
        rt.voice_calibrate = AsyncMock(return_value=312.5)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/calibrate", json={}).json()
        assert data["measured_rms"] == pytest.approx(312.5)

    def test_calibrated_false_when_rms_zero(self, client) -> None:
        rt = MagicMock()
        rt.voice_calibrate = AsyncMock(return_value=0.0)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/calibrate", json={}).json()
        assert data["calibrated"] is False

    def test_duration_s_passed_to_voice_calibrate(self, client) -> None:
        rt = MagicMock()
        rt.voice_calibrate = AsyncMock(return_value=200.0)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.post("/api/v1/voice/calibrate", json={"duration_s": 2.0})
        rt.voice_calibrate.assert_called_once_with(duration_s=2.0)

    def test_default_duration_s_is_one(self, client) -> None:
        rt = MagicMock()
        rt.voice_calibrate = AsyncMock(return_value=200.0)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.post("/api/v1/voice/calibrate", json={})
        rt.voice_calibrate.assert_called_once_with(duration_s=1.0)
