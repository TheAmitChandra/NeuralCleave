"""Tests for POST /api/v1/settings/voice — persists STT config to config.toml.

The endpoint writes stt/stt_model/stt_device to ~/.neuralcleave/config.toml
so they are picked up on the next gateway restart.
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


class TestPostSettingsVoiceValid:
    def test_returns_ok_and_restart_required(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["restart_required"] is True

    def test_updated_fields_listed(self, client):
        r = client.post(
            "/api/v1/settings/voice",
            json={"stt": "whisper", "stt_model": "small", "stt_device": "cpu"},
        )
        assert r.status_code == 200
        assert set(r.json()["updated_fields"]) == {"stt", "stt_model", "stt_device"}

    def test_stt_none_is_accepted(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "none"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_partial_body_only_updates_provided_fields(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt_model": "tiny"})
        assert r.status_code == 200
        assert r.json()["updated_fields"] == ["stt_model"]

    def test_writes_config_toml(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "whisper", "stt_model": "base"})
        config_path = tmp_path / ".neuralcleave" / "config.toml"
        assert config_path.exists()

    def test_written_toml_contains_stt_whisper(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        text = (tmp_path / ".neuralcleave" / "config.toml").read_text()
        assert 'stt = "whisper"' in text

    def test_written_toml_contains_stt_model(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "whisper", "stt_model": "small"})
        text = (tmp_path / ".neuralcleave" / "config.toml").read_text()
        assert 'stt_model = "small"' in text

    def test_written_toml_contains_stt_device(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt_device": "cuda"})
        text = (tmp_path / ".neuralcleave" / "config.toml").read_text()
        assert 'stt_device = "cuda"' in text

    def test_idempotent_repeated_calls(self, client, tmp_path):
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        r2 = client.post("/api/v1/settings/voice", json={"stt": "none"})
        assert r2.status_code == 200
        text = (tmp_path / ".neuralcleave" / "config.toml").read_text()
        assert 'stt = "none"' in text

    def test_preserves_existing_non_voice_keys(self, client, tmp_path):
        # Pre-write a config with an [agent] section
        config_dir = tmp_path / ".neuralcleave"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.toml").write_bytes(b'[agent]\nname = "Alice"\n')
        client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        text = (config_dir / "config.toml").read_text()
        assert 'name = "Alice"' in text
        assert 'stt = "whisper"' in text


class TestPostSettingsVoiceInvalid:
    def test_rejects_unknown_stt_backend(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "openai"})
        assert r.status_code == 422

    def test_rejects_unknown_stt_model(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt_model": "gigantic"})
        assert r.status_code == 422

    def test_rejects_unknown_stt_device(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt_device": "tpu"})
        assert r.status_code == 422

    def test_empty_body_returns_ok(self, client):
        r = client.post("/api/v1/settings/voice", json={})
        assert r.status_code == 200
        assert r.json()["updated_fields"] == []
