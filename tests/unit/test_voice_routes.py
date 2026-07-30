"""Unit tests for GET /voice/config and PATCH /voice/config gateway endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.routes import router

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_runtime(
    stt_model: str = "base",
    stt_device: str = "cpu",
    tts_engine: str = "pyttsx3",
    language: str | None = "en",
) -> MagicMock:
    rt = MagicMock()
    stt = MagicMock()
    stt.model_size = stt_model
    stt.device = stt_device
    stt.language = language
    tts = MagicMock()
    tts._el_key = ""
    tts._el_voice = ""
    rt._stt = stt
    rt._tts = tts
    return rt


# ---------------------------------------------------------------------------
# GET /voice/config
# ---------------------------------------------------------------------------

class TestGetVoiceConfig:
    def test_returns_200_with_runtime(self, client: TestClient) -> None:
        rt = _make_runtime()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            resp = client.get("/api/v1/voice/config")
        assert resp.status_code == 200

    def test_response_fields_present(self, client: TestClient) -> None:
        rt = _make_runtime(stt_model="small", stt_device="cuda", language="fr")
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/config").json()
        assert data["stt_model"] == "small"
        assert data["stt_device"] == "cuda"
        assert data["language"] == "fr"
        assert "tts_engine" in data
        assert "stt_available" in data
        assert "tts_available" in data

    def test_stt_available_true_when_stt_present(self, client: TestClient) -> None:
        rt = _make_runtime()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/config").json()
        assert data["stt_available"] is True

    def test_stt_available_false_when_stt_none(self, client: TestClient) -> None:
        rt = _make_runtime()
        rt._stt = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/config").json()
        assert data["stt_available"] is False

    def test_no_runtime_returns_defaults(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.get("/api/v1/voice/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stt_available"] is False
        assert data["tts_available"] is False


# ---------------------------------------------------------------------------
# PATCH /voice/config
# ---------------------------------------------------------------------------

class TestPatchVoiceConfig:
    def test_patch_tts_engine(self, client: TestClient) -> None:
        rt = _make_runtime()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            resp = client.patch("/api/v1/voice/config", json={"tts_engine": "kokoro"})
        assert resp.status_code == 200
        assert resp.json()["tts_engine"] == "kokoro"

    def test_patch_language(self, client: TestClient) -> None:
        rt = _make_runtime()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            resp = client.patch("/api/v1/voice/config", json={"language": "es"})
        assert resp.status_code == 200

    def test_patch_elevenlabs_voice_id(self, client: TestClient) -> None:
        rt = _make_runtime()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            resp = client.patch("/api/v1/voice/config", json={"elevenlabs_voice_id": "abc123"})
        assert resp.status_code == 200

    def test_patch_empty_body_ok(self, client: TestClient) -> None:
        rt = _make_runtime()
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            resp = client.patch("/api/v1/voice/config", json={})
        assert resp.status_code == 200

    def test_patch_no_runtime_still_200(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.patch("/api/v1/voice/config", json={"tts_engine": "elevenlabs"})
        assert resp.status_code == 200
