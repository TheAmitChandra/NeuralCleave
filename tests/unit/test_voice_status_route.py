"""Tests for GET /voice/status unified snapshot route."""

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


class TestVoiceStatusRoute:
    def test_runtime_available_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/status").json()
        assert data["runtime_available"] is False

    def test_all_false_when_no_runtime(self, client) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/status").json()
        assert data["continuous_listening"] is False
        assert data["ptt_available"] is False
        assert data["is_handoff_active"] is False

    def test_runtime_available_true_when_runtime_present(self, client) -> None:
        rt = MagicMock()
        rt._continuous = None
        rt._wake_detector = None
        rt._ptt = None
        rt._in_handoff = False
        rt._stt = MagicMock()
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/status").json()
        assert data["runtime_available"] is True

    def test_ptt_available_true_when_ptt_configured(self, client) -> None:
        rt = MagicMock()
        rt._ptt = MagicMock(is_recording=False)
        rt._continuous = None
        rt._wake_detector = None
        rt._in_handoff = False
        rt._stt = None
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/status").json()
        assert data["ptt_available"] is True

    def test_ptt_is_recording_true_when_active(self, client) -> None:
        rt = MagicMock()
        rt._ptt = MagicMock(is_recording=True)
        rt._continuous = None
        rt._wake_detector = None
        rt._in_handoff = False
        rt._stt = None
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/status").json()
        assert data["ptt_is_recording"] is True

    def test_stt_available_true_when_stt_configured(self, client) -> None:
        rt = MagicMock()
        rt._ptt = None
        rt._continuous = None
        rt._wake_detector = None
        rt._in_handoff = False
        rt._stt = MagicMock()
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/status").json()
        assert data["stt_available"] is True

    def test_is_handoff_active_reflects_runtime(self, client) -> None:
        rt = MagicMock()
        rt._ptt = None
        rt._continuous = None
        rt._wake_detector = None
        rt._in_handoff = True
        rt._stt = None
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/status").json()
        assert data["is_handoff_active"] is True

    def test_continuous_available_false_when_continuous_not_configured(self, client) -> None:
        """continuous_available must be False when _continuous is None."""
        rt = MagicMock()
        rt._continuous = None
        rt._wake_detector = None
        rt._ptt = None
        rt._in_handoff = False
        rt._stt = None
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/status").json()
        assert data["continuous_available"] is False

    def test_continuous_available_true_when_continuous_configured(self, client) -> None:
        """continuous_available must be True when _continuous subsystem is wired."""
        rt = MagicMock()
        rt._continuous = MagicMock(is_listening=False)
        rt._wake_detector = None
        rt._ptt = None
        rt._in_handoff = False
        rt._stt = None
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/status").json()
        assert data["continuous_available"] is True

    def test_continuous_available_absent_when_no_runtime(self, client) -> None:
        """When the runtime is None the response must still contain continuous_available=False."""
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            data = client.get("/api/v1/voice/status").json()
        assert "continuous_available" not in data or data["continuous_available"] is False
