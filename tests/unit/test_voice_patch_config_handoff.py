"""Tests for PATCH /voice/config wake_handoff_duration_s field."""

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


def _make_rt() -> MagicMock:
    rt = MagicMock()
    rt._tts = None
    rt._stt = None
    rt._continuous = None
    return rt


class TestPatchConfigHandoff:
    def test_calls_set_wake_handoff_duration(self, client) -> None:
        rt = _make_rt()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.patch("/api/v1/voice/config", json={"wake_handoff_duration_s": 15.0})
        rt.set_wake_handoff_duration.assert_called_once_with(15.0)

    def test_field_in_updated_fields(self, client) -> None:
        rt = _make_rt()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch(
                "/api/v1/voice/config", json={"wake_handoff_duration_s": 20.0}
            ).json()
        assert "wake_handoff_duration_s" in data["updated_fields"]

    def test_float_coercion_applied(self, client) -> None:
        rt = _make_rt()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.patch("/api/v1/voice/config", json={"wake_handoff_duration_s": 5})
        rt.set_wake_handoff_duration.assert_called_once_with(5.0)

    def test_not_called_when_key_absent(self, client) -> None:
        rt = _make_rt()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.patch("/api/v1/voice/config", json={})
        rt.set_wake_handoff_duration.assert_not_called()

    def test_zero_handoff_accepted(self, client) -> None:
        rt = _make_rt()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch(
                "/api/v1/voice/config", json={"wake_handoff_duration_s": 0.0}
            ).json()
        assert "wake_handoff_duration_s" in data["updated_fields"]

    def test_applied_true_when_runtime_present(self, client) -> None:
        rt = _make_rt()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch(
                "/api/v1/voice/config", json={"wake_handoff_duration_s": 10.0}
            ).json()
        assert data["applied"] is True
