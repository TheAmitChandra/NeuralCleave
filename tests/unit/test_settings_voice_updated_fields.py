"""Tests for the updated_fields list returned by POST /settings/voice.

The frontend uses updated_fields to show which settings were saved.
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


class TestUpdatedFields:
    def test_stt_only(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert r.json()["updated_fields"] == ["stt"]

    def test_stt_and_model(self, client):
        r = client.post(
            "/api/v1/settings/voice",
            json={"stt": "whisper", "stt_model": "base"},
        )
        fields = r.json()["updated_fields"]
        assert "stt" in fields
        assert "stt_model" in fields

    def test_all_three_fields(self, client):
        r = client.post(
            "/api/v1/settings/voice",
            json={"stt": "whisper", "stt_model": "small", "stt_device": "cpu"},
        )
        fields = r.json()["updated_fields"]
        assert set(fields) == {"stt", "stt_model", "stt_device"}

    def test_device_only(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt_device": "cuda"})
        assert r.json()["updated_fields"] == ["stt_device"]

    def test_empty_body_returns_empty_fields(self, client):
        r = client.post("/api/v1/settings/voice", json={})
        assert r.json()["updated_fields"] == []
