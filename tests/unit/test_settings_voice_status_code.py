"""Tests for HTTP status codes from POST /settings/voice."""

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


class TestStatusCodes:
    def test_valid_request_returns_200(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert r.status_code == 200

    def test_empty_body_returns_200(self, client):
        r = client.post("/api/v1/settings/voice", json={})
        assert r.status_code == 200

    def test_invalid_stt_returns_422(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "azure"})
        assert r.status_code == 422

    def test_content_type_is_json(self, client):
        r = client.post("/api/v1/settings/voice", json={"stt": "whisper"})
        assert "application/json" in r.headers.get("content-type", "")
