"""Tests for MCP client gateway routes: POST/GET/DELETE /api/v1/mcp/clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.main import create_app
from neuralcleave.tools.registry import ToolRegistry


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def _runtime_with_registry(registry: ToolRegistry) -> MagicMock:
    runtime = MagicMock()
    runtime._pipeline._tool_registry = registry
    return runtime


class TestMcpClientConnect:
    def test_connect_returns_201_with_tool_names(self, client: TestClient) -> None:
        registry = ToolRegistry()
        with (
            patch("neuralcleave.gateway.routes.get_runtime", return_value=_runtime_with_registry(registry)),
            patch("neuralcleave.mcp.client_manager.MCP_CLIENTS.connect", new=AsyncMock(return_value=["mcp_acme_search"])),
        ):
            resp = client.post("/api/v1/mcp/clients", json={"name": "acme", "command": ["python", "-m", "x"]})

        assert resp.status_code == 201
        assert resp.json() == {"name": "acme", "tools": ["mcp_acme_search"]}

    def test_connect_missing_name_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/mcp/clients", json={"command": ["python"]})
        assert resp.status_code == 422

    def test_connect_missing_command_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/mcp/clients", json={"name": "acme"})
        assert resp.status_code == 422

    def test_connect_without_runtime_returns_503(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.post("/api/v1/mcp/clients", json={"name": "acme", "command": ["python"]})
        assert resp.status_code == 503

    def test_connect_duplicate_name_returns_409(self, client: TestClient) -> None:
        registry = ToolRegistry()
        with (
            patch("neuralcleave.gateway.routes.get_runtime", return_value=_runtime_with_registry(registry)),
            patch(
                "neuralcleave.mcp.client_manager.MCP_CLIENTS.connect",
                new=AsyncMock(side_effect=ValueError("MCP client 'acme' is already connected")),
            ),
        ):
            resp = client.post("/api/v1/mcp/clients", json={"name": "acme", "command": ["python"]})
        assert resp.status_code == 409

    def test_connect_failure_returns_502(self, client: TestClient) -> None:
        registry = ToolRegistry()
        with (
            patch("neuralcleave.gateway.routes.get_runtime", return_value=_runtime_with_registry(registry)),
            patch(
                "neuralcleave.mcp.client_manager.MCP_CLIENTS.connect",
                new=AsyncMock(side_effect=RuntimeError("subprocess failed to start")),
            ),
        ):
            resp = client.post("/api/v1/mcp/clients", json={"name": "acme", "command": ["python"]})
        assert resp.status_code == 502


class TestMcpClientList:
    def test_list_returns_connected_clients(self, client: TestClient) -> None:
        with patch(
            "neuralcleave.mcp.client_manager.MCP_CLIENTS.list_clients",
            return_value={"acme": ["mcp_acme_search"]},
        ):
            resp = client.get("/api/v1/mcp/clients")

        assert resp.status_code == 200
        assert resp.json() == {"clients": {"acme": ["mcp_acme_search"]}}

    def test_list_empty_when_none_connected(self, client: TestClient) -> None:
        with patch("neuralcleave.mcp.client_manager.MCP_CLIENTS.list_clients", return_value={}):
            resp = client.get("/api/v1/mcp/clients")
        assert resp.json() == {"clients": {}}


class TestMcpClientDisconnect:
    def test_disconnect_returns_200_when_connected(self, client: TestClient) -> None:
        registry = ToolRegistry()
        with (
            patch("neuralcleave.gateway.routes.get_runtime", return_value=_runtime_with_registry(registry)),
            patch("neuralcleave.mcp.client_manager.MCP_CLIENTS.disconnect", new=AsyncMock(return_value=True)),
        ):
            resp = client.delete("/api/v1/mcp/clients/acme")

        assert resp.status_code == 200
        assert resp.json() == {"disconnected": True, "name": "acme"}

    def test_disconnect_unknown_name_returns_404(self, client: TestClient) -> None:
        registry = ToolRegistry()
        with (
            patch("neuralcleave.gateway.routes.get_runtime", return_value=_runtime_with_registry(registry)),
            patch("neuralcleave.mcp.client_manager.MCP_CLIENTS.disconnect", new=AsyncMock(return_value=False)),
        ):
            resp = client.delete("/api/v1/mcp/clients/nope")

        assert resp.status_code == 404

    def test_disconnect_without_runtime_returns_503(self, client: TestClient) -> None:
        with patch("neuralcleave.gateway.routes.get_runtime", return_value=None):
            resp = client.delete("/api/v1/mcp/clients/acme")
        assert resp.status_code == 503
