"""Tests for is_handoff_active and wake_handoff_duration_s in GET /voice/config."""

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


def _make_rt(*, in_handoff: bool = False, duration: float = 10.0):
    rt = MagicMock()
    rt._in_handoff = in_handoff
    rt._wake_handoff_duration_s = duration
    rt._continuous = None
    rt._stt = None
    rt._tts = None
    return rt


class TestVoiceConfigHandoffFields:
    def test_is_handoff_active_false_when_not_in_handoff(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=_make_rt(in_handoff=False)):
            data = client.get("/api/v1/voice/config").json()
        assert data["is_handoff_active"] is False

    def test_is_handoff_active_true_when_in_handoff(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=_make_rt(in_handoff=True)):
            data = client.get("/api/v1/voice/config").json()
        assert data["is_handoff_active"] is True

    def test_wake_handoff_duration_s_returned(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=_make_rt(duration=20.0)):
            data = client.get("/api/v1/voice/config").json()
        assert data["wake_handoff_duration_s"] == 20.0

    def test_wake_handoff_duration_default(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=_make_rt(duration=10.0)):
            data = client.get("/api/v1/voice/config").json()
        assert data["wake_handoff_duration_s"] == 10.0

    def test_is_handoff_active_default_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/config").json()
        assert data["is_handoff_active"] is False

    def test_wake_handoff_duration_default_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/config").json()
        assert data["wake_handoff_duration_s"] == 10.0
