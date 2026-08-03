"""Tests for invalid input rejection in POST /settings/voice."""

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
    return TestClient(app, raise_server_exceptions=False)


class TestInvalidInputs:
    def test_unknown_stt_backend_rejected(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "google"})
        assert r.status_code == 422

    def test_empty_string_stt_rejected(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": ""})
        assert r.status_code == 422

    def test_integer_stt_rejected(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": 1})
        assert r.status_code == 422

    def test_stt_openai_rejected(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "openai"})
        assert r.status_code == 422
