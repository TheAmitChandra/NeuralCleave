"""Tests that POST /settings/voice rejects wrong HTTP methods."""

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


class TestHttpMethods:
    def test_get_not_allowed(self, client):
        r = client.get("/api/v1/settings/voice")
        assert r.status_code == 405

    def test_put_not_allowed(self, client):
        r = client.put("/api/v1/settings/voice", json={"stt": "whisper"})
        assert r.status_code == 405

    def test_delete_not_allowed(self, client):
        r = client.delete("/api/v1/settings/voice")
        assert r.status_code == 405
