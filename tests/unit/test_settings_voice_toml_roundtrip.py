"""Verify that POST /settings/voice writes valid TOML that load_config can parse back."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from neuralcleave.config import NeuralCleaveConfig, load_config
from neuralcleave.gateway.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cfg = NeuralCleaveConfig()
    app = create_app(cfg)
    return TestClient(app, raise_server_exceptions=True)


def test_written_toml_is_parseable_by_load_config(client, tmp_path):
    client.post(
        "/api/v1/settings/voice",
        json={"stt": "whisper", "stt_model": "small", "stt_device": "cpu"},
    )
    config_path = tmp_path / ".neuralcleave" / "config.toml"
    parsed = load_config(config_path)
    assert parsed.voice.stt == "whisper"
    assert parsed.voice.stt_model == "small"
    assert parsed.voice.stt_device == "cpu"


def test_stt_none_parsed_correctly(client, tmp_path):
    client.post("/api/v1/settings/voice", json={"stt": "none"})
    config_path = tmp_path / ".neuralcleave" / "config.toml"
    parsed = load_config(config_path)
    assert parsed.voice.stt == "none"


def test_sequential_writes_last_value_wins(client, tmp_path):
    client.post("/api/v1/settings/voice", json={"stt": "whisper"})
    client.post("/api/v1/settings/voice", json={"stt": "none"})
    config_path = tmp_path / ".neuralcleave" / "config.toml"
    parsed = load_config(config_path)
    assert parsed.voice.stt == "none"


def test_partial_write_does_not_reset_other_voice_fields(client, tmp_path):
    client.post("/api/v1/settings/voice", json={"stt": "whisper", "stt_model": "medium"})
    client.post("/api/v1/settings/voice", json={"stt_device": "cuda"})
    config_path = tmp_path / ".neuralcleave" / "config.toml"
    parsed = load_config(config_path)
    assert parsed.voice.stt == "whisper"
    assert parsed.voice.stt_model == "medium"
    assert parsed.voice.stt_device == "cuda"
