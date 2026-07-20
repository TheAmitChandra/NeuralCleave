"""Verify that every REST endpoint called by a frontend page actually exists
and returns the expected shape.

These tests are the source-of-truth contract between the Next.js pages and
the FastAPI backend. If a page calls the wrong URL this file will catch it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import neuralcleave.canvas.routes as canvas_routes_module
import neuralcleave.gateway.routes as routes_module
from neuralcleave.canvas.renderer import CanvasRenderer
from neuralcleave.canvas.routes import api_router as canvas_api_router
from neuralcleave.canvas.routes import page_router as canvas_page_router
from neuralcleave.gateway.routes import router as api_router

# ---------------------------------------------------------------------------
# App fixture — wires all routers the same way main.py does
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset():
    canvas_routes_module.set_canvas_renderer(None)
    yield
    canvas_routes_module.set_canvas_renderer(None)


@pytest.fixture()
def app():
    application = FastAPI()
    application.include_router(api_router)  # /api/v1/*
    application.include_router(canvas_api_router, prefix="/api/v1")  # /api/v1/canvas/*
    application.include_router(canvas_page_router)
    return application


@pytest.fixture()
def client(app):
    with patch.object(routes_module, "_orchestrator", None):
        with patch.object(routes_module, "_hub_installer", None):
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c


@pytest.fixture()
def renderer():
    r = CanvasRenderer()
    canvas_routes_module.set_canvas_renderer(r)
    return r


# ===========================================================================
# Canvas page — calls GET /api/v1/canvas/state and GET /api/v1/canvas/status
# ===========================================================================


class TestCanvasPageEndpoints:
    def test_canvas_state_endpoint_exists(self, client):
        r = client.get("/api/v1/canvas/state")
        assert r.status_code == 200

    def test_canvas_state_has_blocks_key(self, client):
        r = client.get("/api/v1/canvas/state")
        assert "blocks" in r.json()

    def test_canvas_state_has_count_key(self, client):
        r = client.get("/api/v1/canvas/state")
        assert "count" in r.json()

    def test_canvas_state_available_key_when_no_renderer(self, client):
        r = client.get("/api/v1/canvas/state")
        data = r.json()
        assert "available" in data
        assert data["available"] is False

    def test_canvas_state_with_renderer_is_available(self, client, renderer):
        r = client.get("/api/v1/canvas/state")
        assert r.json()["available"] is True

    def test_canvas_state_blocks_is_list(self, client):
        r = client.get("/api/v1/canvas/state")
        assert isinstance(r.json()["blocks"], list)

    def test_canvas_status_endpoint_exists(self, client):
        r = client.get("/api/v1/canvas/status")
        assert r.status_code == 200

    def test_canvas_status_has_available_key(self, client):
        r = client.get("/api/v1/canvas/status")
        assert "available" in r.json()

    # Verify the WRONG endpoint (snapshot) does NOT exist — the page must not
    # call it.
    def test_canvas_snapshot_does_not_exist(self, client):
        r = client.get("/api/v1/canvas/snapshot")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_canvas_state_returns_blocks_after_render(self, client, renderer):
        from neuralcleave.canvas.block import CanvasBlock

        block = CanvasBlock(
            id="b1",
            block_type="text",
            content="Hello canvas",
            title="Test",
            created_at="2026-07-16T00:00:00Z",
        )
        await renderer.add_block(block)
        r = client.get("/api/v1/canvas/state")
        data = r.json()
        assert data["count"] == 1
        assert data["blocks"][0]["block_type"] == "text"
        assert data["blocks"][0]["content"] == "Hello canvas"


# ===========================================================================
# Skills page — calls GET /api/v1/hub/packages
# ===========================================================================


class TestSkillsPageEndpoints:
    def test_hub_packages_endpoint_exists(self, client):
        r = client.get("/api/v1/hub/packages")
        assert r.status_code == 200

    def test_hub_packages_has_packages_key(self, client):
        r = client.get("/api/v1/hub/packages")
        assert "packages" in r.json()

    def test_hub_packages_has_available_key(self, client):
        r = client.get("/api/v1/hub/packages")
        assert "available" in r.json()

    def test_hub_packages_is_list(self, client):
        r = client.get("/api/v1/hub/packages")
        assert isinstance(r.json()["packages"], list)

    def test_hub_status_endpoint_exists(self, client):
        r = client.get("/api/v1/hub/status")
        assert r.status_code == 200

    def test_hub_status_has_available_key(self, client):
        r = client.get("/api/v1/hub/status")
        assert "available" in r.json()

    # Verify the WRONG endpoint (skills) does NOT exist.
    def test_skills_endpoint_does_not_exist(self, client):
        r = client.get("/api/v1/skills")
        assert r.status_code == 404


# ===========================================================================
# Orchestrator page — calls GET /api/v1/orchestrator/status and
#   GET /api/v1/orchestrator/nodes/{name}/memory
# ===========================================================================


class TestOrchestratorPageEndpoints:
    def test_orchestrator_status_exists(self, client):
        r = client.get("/api/v1/orchestrator/status")
        assert r.status_code == 200

    def test_orchestrator_status_has_expected_keys(self, client):
        data = client.get("/api/v1/orchestrator/status").json()
        assert "available" in data

    def test_orchestrator_nodes_list_exists(self, client):
        r = client.get("/api/v1/orchestrator/nodes")
        assert r.status_code == 200

    def test_orchestrator_nodes_has_nodes_key(self, client):
        r = client.get("/api/v1/orchestrator/nodes")
        assert "nodes" in r.json()

    def test_orchestrator_namespaces_exists(self, client):
        r = client.get("/api/v1/orchestrator/namespaces")
        assert r.status_code == 200


# ===========================================================================
# Dashboard page — calls /status, /channels, /memory/entries, /metrics/snapshot
# ===========================================================================


class TestDashboardPageEndpoints:
    def test_status_endpoint_exists(self, client):
        assert client.get("/api/v1/status").status_code == 200

    def test_status_has_version(self, client):
        assert "version" in client.get("/api/v1/status").json()

    def test_metrics_snapshot_exists(self, client):
        assert client.get("/api/v1/metrics/snapshot").status_code == 200
