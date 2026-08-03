"""Tests for stt_device values accepted by POST /settings/voice."""

from __future__ import annotations

import tomllib
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


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_valid_stt_device_accepted(client, tmp_path, device):
    r = client.post("/api/v1/settings/voice", json={"stt": "whisper", "stt_device": device})
    assert r.status_code == 200
    config_path = tmp_path / ".neuralcleave" / "config.toml"
    with open(config_path, "rb") as fh:
        data = tomllib.load(fh)
    assert data["voice"]["stt_device"] == device
