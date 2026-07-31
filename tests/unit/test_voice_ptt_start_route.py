"""Tests for POST /voice/ptt/start route."""

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


class TestPttStartRoute:
    def test_returns_started_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/ptt/start").json()
        assert data["started"] is False

    def test_returns_started_true_when_ptt_starts(self, client) -> None:
        rt = MagicMock()
        rt.ptt_start = AsyncMock(return_value=True)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/ptt/start").json()
        assert data["started"] is True

    def test_returns_started_false_when_ptt_fails(self, client) -> None:
        rt = MagicMock()
        rt.ptt_start = AsyncMock(return_value=False)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/ptt/start").json()
        assert data["started"] is False

    def test_reason_present_when_not_started(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/ptt/start").json()
        assert "reason" in data

    def test_calls_rt_ptt_start(self, client) -> None:
        rt = MagicMock()
        rt.ptt_start = AsyncMock(return_value=True)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            client.post("/api/v1/voice/ptt/start")
        rt.ptt_start.assert_called_once()
