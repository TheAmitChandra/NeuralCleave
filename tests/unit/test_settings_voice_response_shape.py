"""Tests for the response body shape of POST /settings/voice."""

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


class TestResponseShape:
    def test_response_has_ok_key(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert "ok" in r.json()

    def test_response_has_restart_required_key(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert "restart_required" in r.json()

    def test_response_has_updated_fields_key(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert "updated_fields" in r.json()

    def test_ok_is_boolean_true(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert r.json()["ok"] is True

    def test_updated_fields_is_list(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert isinstance(r.json()["updated_fields"], list)
