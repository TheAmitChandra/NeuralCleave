"""Tests for POST /api/v1/voice/listen/start, stop, and GET /voice/listen/status."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.routes import router


@pytest.fixture()
def client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_cont(*, is_listening: bool = False) -> MagicMock:
    cont = MagicMock()
    cont.is_listening = is_listening
    cont.start = AsyncMock()
    cont.stop = AsyncMock()
    return cont


def _make_runtime(*, cont=None) -> MagicMock:
    rt = MagicMock()
    rt._continuous = cont
    return rt


# ---------------------------------------------------------------------------
# GET /voice/listen/status
# ---------------------------------------------------------------------------


class TestGetListenStatus:
    def test_returns_200(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.get("/api/v1/voice/listen/status")
        assert resp.status_code == 200

    def test_not_listening_when_no_runtime(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/listen/status").json()
        assert data["continuous_listening"] is False
        assert data["continuous_available"] is False

    def test_not_available_when_no_continuous(self, client: TestClient) -> None:
        rt = _make_runtime(cont=None)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/listen/status").json()
        assert data["continuous_available"] is False

    def test_listening_true_when_active(self, client: TestClient) -> None:
        rt = _make_runtime(cont=_make_cont(is_listening=True))
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/listen/status").json()
        assert data["continuous_available"] is True
        assert data["continuous_listening"] is True

    def test_listening_false_when_not_active(self, client: TestClient) -> None:
        rt = _make_runtime(cont=_make_cont(is_listening=False))
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/listen/status").json()
        assert data["continuous_listening"] is False


# ---------------------------------------------------------------------------
# POST /voice/listen/start
# ---------------------------------------------------------------------------


class TestPostListenStart:
    def test_returns_200(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.post("/api/v1/voice/listen/start")
        assert resp.status_code == 200

    def test_no_runtime_returns_not_started(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/listen/start").json()
        assert data["started"] is False
        assert "runtime" in data["reason"]

    def test_no_continuous_returns_not_started(self, client: TestClient) -> None:
        rt = _make_runtime(cont=None)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/listen/start").json()
        assert data["started"] is False
        assert "continuous" in data["reason"]

    def test_starts_when_not_listening(self, client: TestClient) -> None:
        cont = _make_cont(is_listening=False)
        rt = _make_runtime(cont=cont)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/listen/start").json()
        assert data["started"] is True
        assert data["already_running"] is False
        cont.start.assert_awaited_once()

    def test_already_running_no_double_start(self, client: TestClient) -> None:
        cont = _make_cont(is_listening=True)
        rt = _make_runtime(cont=cont)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/listen/start").json()
        assert data["started"] is True
        assert data["already_running"] is True
        cont.start.assert_not_awaited()


# ---------------------------------------------------------------------------
# POST /voice/listen/stop
# ---------------------------------------------------------------------------


class TestPostListenStop:
    def test_returns_200(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.post("/api/v1/voice/listen/stop")
        assert resp.status_code == 200

    def test_no_runtime_returns_not_stopped(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.post("/api/v1/voice/listen/stop").json()
        assert data["stopped"] is False

    def test_no_continuous_returns_not_stopped(self, client: TestClient) -> None:
        rt = _make_runtime(cont=None)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/listen/stop").json()
        assert data["stopped"] is False

    def test_stops_when_listening(self, client: TestClient) -> None:
        cont = _make_cont(is_listening=True)
        rt = _make_runtime(cont=cont)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/listen/stop").json()
        assert data["stopped"] is True
        assert data["already_stopped"] is False
        cont.stop.assert_awaited_once()

    def test_already_stopped_no_double_stop(self, client: TestClient) -> None:
        cont = _make_cont(is_listening=False)
        rt = _make_runtime(cont=cont)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.post("/api/v1/voice/listen/stop").json()
        assert data["stopped"] is True
        assert data["already_stopped"] is True
        cont.stop.assert_not_awaited()
