"""Tests that multiple sequential writes to config.toml end in a consistent state.

The restart_backend flow means the gateway is killed and relaunched; any
pending writes must be complete before respawn. These tests verify that
sequential POSTs leave the file in the state matching the last write.
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


class TestSequentialWrites:
    def test_last_write_wins_for_stt(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        client.post("/api/v1/settings/voice", json={"stt": "none"})
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["stt"] == "whisper"

    def test_last_write_wins_for_model(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt_model": "base"})
        client.post("/api/v1/settings/voice", json={"stt_model": "large-v3"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["stt_model"] == "large-v3"

    def test_ten_writes_end_consistent(self, client, tmp_path):
        for i in range(10):
            stt = "whisper" if i % 2 == 0 else "none"
            client.post("/api/v1/settings/voice", json={"stt": stt})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["stt"] == "none"
