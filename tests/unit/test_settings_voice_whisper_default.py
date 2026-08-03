"""Tests confirming that the gateway config defaults stt to 'none' at the model level
while the frontend overrides this to 'whisper' for new installs.

The gateway reads whatever is stored in config.toml; it does NOT enforce a default
of 'whisper'. The default is set in the frontend DEFAULTS constant. These tests
confirm the endpoint correctly persists whatever the frontend sends.
"""

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


class TestWhisperDefaultPersistence:
    def test_whisper_written_to_toml(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["stt"] == "whisper"

    def test_overwrite_whisper_with_none(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        client.post("/api/v1/settings/voice", json={"stt": "none"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["stt"] == "none"

    def test_overwrite_none_with_whisper(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "none"})
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["stt"] == "whisper"
