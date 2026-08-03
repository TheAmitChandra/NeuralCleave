"""Tests that POST /settings/voice merges into existing config without clobbering other sections."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import tomli_w
from fastapi.testclient import TestClient

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.gateway.main import create_app


@pytest.fixture()
def client_with_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    config_dir = tmp_path / ".neuralcleave"
    config_dir.mkdir(parents=True, exist_ok=True)
    existing = {
        "llm": {"provider": "deepseek", "model": "deepseek-chat"},
        "voice": {"volume": 0.8, "stt": "none"},
    }
    with open(config_dir / "config.toml", "wb") as fh:
        tomli_w.dump(existing, fh)
    cfg = NeuralCleaveConfig()
    app = create_app(cfg)
    return TestClient(app, raise_server_exceptions=True), tmp_path


class TestConfigPreservation:
    def test_llm_section_preserved_after_voice_write(self, client_with_existing):
        client, tmp_path = client_with_existing
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["llm"]["provider"] == "deepseek"
        assert data["llm"]["model"] == "deepseek-chat"

    def test_existing_voice_volume_preserved(self, client_with_existing):
        client, tmp_path = client_with_existing
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["volume"] == pytest.approx(0.8)

    def test_stt_key_updated_in_voice_section(self, client_with_existing):
        client, tmp_path = client_with_existing
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
        assert data["voice"]["stt"] == "whisper"
