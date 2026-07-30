"""Tests for vad_backend in VoiceConfig and REST config endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from neuralcleave.config import VoiceConfig, load_config
from neuralcleave.gateway.routes import router


@pytest.fixture()
def client() -> TestClient:
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_runtime(*, vad_backend: str = "energy", threshold: float = 300.0) -> MagicMock:
    rt = MagicMock()
    vad = MagicMock()
    vad.backend = vad_backend
    vad.threshold_rms = threshold
    cont = MagicMock()
    cont._vad = vad
    cont.is_listening = False
    rt._continuous = cont
    rt._stt = None
    rt._tts = None
    return rt


class TestVoiceConfigVadBackend:
    def test_default_vad_backend_is_energy(self) -> None:
        cfg = VoiceConfig()
        assert cfg.vad_backend == "energy"

    def test_vad_backend_loaded_from_toml(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[voice]\nvad_backend = 'webrtcvad'\n")
        cfg = load_config(str(f))
        assert cfg.voice.vad_backend == "webrtcvad"

    def test_vad_backend_defaults_when_missing(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[agent]\nname = 'NC'\n")
        cfg = load_config(str(f))
        assert cfg.voice.vad_backend == "energy"


class TestGetVoiceConfigVadBackend:
    def test_returns_vad_backend_from_runtime(self, client: TestClient) -> None:
        rt = _make_runtime(vad_backend="energy")
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/config").json()
        assert data["vad_backend"] == "energy"

    def test_no_runtime_still_returns_200(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.get("/api/v1/voice/config")
        assert resp.status_code == 200

    def test_no_continuous_defaults_to_energy(self, client: TestClient) -> None:
        rt = MagicMock()
        rt._continuous = None
        rt._stt = None
        rt._tts = None
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/config").json()
        assert data.get("vad_backend") == "energy"


class TestPatchVoiceConfigVadThreshold:
    def test_patch_vad_silence_threshold_updates_vad(self, client: TestClient) -> None:
        rt = _make_runtime(threshold=300.0)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch(
                "/api/v1/voice/config",
                json={"vad_silence_threshold": 500.0},
            ).json()
        assert "vad_silence_threshold" in data["updated_fields"]
        assert rt._continuous._vad.threshold_rms == pytest.approx(500.0)

    def test_patch_returns_vad_backend(self, client: TestClient) -> None:
        rt = _make_runtime(vad_backend="energy")
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch("/api/v1/voice/config", json={}).json()
        assert data["vad_backend"] == "energy"

    def test_patch_without_vad_field_does_not_update(self, client: TestClient) -> None:
        rt = _make_runtime(threshold=300.0)
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.patch("/api/v1/voice/config", json={}).json()
        assert "vad_silence_threshold" not in data["updated_fields"]
