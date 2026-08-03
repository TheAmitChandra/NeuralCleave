"""POST /settings/voice creates ~/.neuralcleave/ when it does not exist."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.gateway.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cfg = NeuralCleaveConfig()
    app = create_app(cfg)
    return TestClient(app, raise_server_exceptions=True)


def test_creates_config_dir_when_missing(client, tmp_path):
    config_dir = tmp_path / ".neuralcleave"
    assert not config_dir.exists()
    r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
    assert r.status_code == 200
    assert config_dir.exists()


def test_creates_config_toml_when_dir_missing(client, tmp_path):
    r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
    assert r.status_code == 200
    assert (tmp_path / ".neuralcleave" / "config.toml").exists()


def test_stt_model_large_v3_accepted(client):
    r = client.post("/api/v1/settings/voice", json={"stt_model": "large-v3"})
    assert r.status_code == 200


def test_stt_device_cuda_accepted(client):
    r = client.post("/api/v1/settings/voice", json={"stt_device": "cuda"})
    assert r.status_code == 200
