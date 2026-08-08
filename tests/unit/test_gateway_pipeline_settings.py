"""Tests for POST /api/v1/settings/pipeline gateway endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.main import create_app
from neuralcleave.gateway.routes import set_runtime


@pytest.fixture(autouse=True)
def reset_runtime():
    set_runtime(None)
    yield
    set_runtime(None)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _make_runtime_with_pipeline(max_tool_steps: int = 5) -> MagicMock:
    pipeline = MagicMock()
    pipeline._max_tool_steps = max_tool_steps
    rt = MagicMock()
    rt._pipeline = pipeline
    return rt


class TestPipelineSettingsEndpoint:
    def test_returns_503_when_no_runtime(self, client: TestClient) -> None:
        resp = client.post("/api/v1/settings/pipeline", json={"max_tool_steps": 3})
        assert resp.status_code == 503

    def test_max_tool_steps_applied_to_pipeline(self, client: TestClient) -> None:
        rt = _make_runtime_with_pipeline()
        set_runtime(rt)

        resp = client.post("/api/v1/settings/pipeline", json={"max_tool_steps": 3})
        assert resp.status_code == 200
        assert resp.json()["applied"] is True
        assert rt._pipeline._max_tool_steps == 3

    def test_max_tool_steps_in_updated_fields(self, client: TestClient) -> None:
        set_runtime(_make_runtime_with_pipeline())
        resp = client.post("/api/v1/settings/pipeline", json={"max_tool_steps": 2})
        assert "max_tool_steps" in resp.json()["updated_fields"]

    def test_max_tool_steps_below_1_returns_422(self, client: TestClient) -> None:
        set_runtime(_make_runtime_with_pipeline())
        resp = client.post("/api/v1/settings/pipeline", json={"max_tool_steps": 0})
        assert resp.status_code == 422

    def test_max_tool_steps_above_20_returns_422(self, client: TestClient) -> None:
        set_runtime(_make_runtime_with_pipeline())
        resp = client.post("/api/v1/settings/pipeline", json={"max_tool_steps": 21})
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client: TestClient) -> None:
        set_runtime(_make_runtime_with_pipeline())
        resp = client.post("/api/v1/settings/pipeline", json={})
        assert resp.status_code == 422

    def test_unknown_field_returns_422(self, client: TestClient) -> None:
        set_runtime(_make_runtime_with_pipeline())
        resp = client.post("/api/v1/settings/pipeline", json={"unknown_setting": "x"})
        assert resp.status_code == 422

    def test_max_tool_steps_of_1_is_valid(self, client: TestClient) -> None:
        set_runtime(_make_runtime_with_pipeline())
        resp = client.post("/api/v1/settings/pipeline", json={"max_tool_steps": 1})
        assert resp.status_code == 200

    def test_max_tool_steps_of_20_is_valid(self, client: TestClient) -> None:
        set_runtime(_make_runtime_with_pipeline())
        resp = client.post("/api/v1/settings/pipeline", json={"max_tool_steps": 20})
        assert resp.status_code == 200
