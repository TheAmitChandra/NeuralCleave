"""Tests for PATCH /voice/config vad_silence_duration_s field."""

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


def _make_rt_with_cont(silence_duration_s: float = 0.8) -> MagicMock:
    cont = MagicMock()
    cont._silence_duration_s = silence_duration_s
    rt = MagicMock()
    rt._continuous = cont
    rt._tts = None
    rt._stt = None
    return rt


class TestPatchConfigVadDuration:
    def test_returns_applied_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.patch("/api/v1/voice/config", json={}).json()
        assert data["applied"] is False

    def test_calls_set_silence_duration_on_cont(self, client) -> None:
        rt = _make_rt_with_cont()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.patch("/api/v1/voice/config", json={"vad_silence_duration_s": 1.2})
        rt._continuous.set_silence_duration.assert_called_once_with(1.2)

    def test_field_in_updated_fields(self, client) -> None:
        rt = _make_rt_with_cont()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch(
                "/api/v1/voice/config", json={"vad_silence_duration_s": 1.5}
            ).json()
        assert "vad_silence_duration_s" in data["updated_fields"]

    def test_not_in_updated_fields_when_no_cont(self, client) -> None:
        rt = MagicMock()
        rt._continuous = None
        rt._tts = None
        rt._stt = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch(
                "/api/v1/voice/config", json={"vad_silence_duration_s": 1.5}
            ).json()
        assert "vad_silence_duration_s" not in data["updated_fields"]

    def test_float_coercion_applied(self, client) -> None:
        rt = _make_rt_with_cont()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.patch("/api/v1/voice/config", json={"vad_silence_duration_s": 2})
        rt._continuous.set_silence_duration.assert_called_once_with(2.0)

    def test_zero_duration_accepted(self, client) -> None:
        rt = _make_rt_with_cont()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch(
                "/api/v1/voice/config", json={"vad_silence_duration_s": 0.0}
            ).json()
        assert "vad_silence_duration_s" in data["updated_fields"]
