"""Tests confirming POST /settings/voice always signals restart_required.

The Tauri restart_backend command uses this flag to decide whether to kill
and respawn the sidecar after a settings write.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.gateway.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cfg = NeuralCleaveConfig()
    app = create_app(cfg)
    return TestClient(app, raise_server_exceptions=True)


class TestRestartRequiredFlag:
    def test_whisper_backend_returns_restart_required(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert r.status_code == 200
        assert r.json()["restart_required"] is True

    def test_none_backend_returns_restart_required(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "none"})
        assert r.status_code == 200
        assert r.json()["restart_required"] is True

    def test_model_only_update_returns_restart_required(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt_model": "large-v3"})
        assert r.status_code == 200
        assert r.json()["restart_required"] is True

    def test_device_only_update_returns_restart_required(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt_device": "cuda"})
        assert r.status_code == 200
        assert r.json()["restart_required"] is True
