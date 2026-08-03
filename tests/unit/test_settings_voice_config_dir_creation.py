"""Tests that POST /settings/voice creates the ~/.neuralcleave dir if it doesn't exist."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.gateway.main import create_app


@pytest.fixture()
def fresh_client(tmp_path, monkeypatch):
    """Client with a home dir that has no .neuralcleave directory yet."""
    home = tmp_path / "clean_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    cfg = NeuralCleaveConfig()
    app = create_app(cfg)
    return TestClient(app, raise_server_exceptions=True), home


class TestConfigDirCreation:
    def test_creates_neuralcleave_dir_when_missing(self, fresh_client):
        client, home = fresh_client
        assert not (home / ".neuralcleave").exists()
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert (home / ".neuralcleave").is_dir()

    def test_creates_config_toml_when_missing(self, fresh_client):
        client, home = fresh_client
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert (home / ".neuralcleave" / "config.toml").is_file()

    def test_returns_200_on_first_write(self, fresh_client):
        client, home = fresh_client
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert r.status_code == 200
