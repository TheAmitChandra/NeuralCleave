"""Tests for MCP gateway routes: /api/v1/mcp/spawn, /status, DELETE /server."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.main import create_app


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


class TestMcpGatewayRoutes:
    def test_mcp_status_returns_not_running_by_default(self, client: TestClient) -> None:
        with patch("neuralcleave.mcp.spawn.MCP_PROCESS") as mock_proc:
            mock_proc.status.return_value = {"running": False, "pid": None}
            resp = client.get("/api/v1/mcp/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False

    def test_mcp_spawn_returns_201_with_pid(self, client: TestClient) -> None:
        with patch("neuralcleave.mcp.spawn.MCP_PROCESS") as mock_proc:
            mock_proc.is_running = False
            mock_proc.spawn.return_value = 1234
            resp = client.post("/api/v1/mcp/spawn")
        assert resp.status_code == 201
        data = resp.json()
        assert data["pid"] == 1234

    def test_mcp_spawn_sets_running_true(self, client: TestClient) -> None:
        with patch("neuralcleave.mcp.spawn.MCP_PROCESS") as mock_proc:
            mock_proc.is_running = False
            mock_proc.spawn.return_value = 5678
            resp = client.post("/api/v1/mcp/spawn")
        assert resp.json()["running"] is True

    def test_mcp_spawn_already_running_flags_already_running(self, client: TestClient) -> None:
        with patch("neuralcleave.mcp.spawn.MCP_PROCESS") as mock_proc:
            mock_proc.is_running = True
            mock_proc.spawn.return_value = 9999
            resp = client.post("/api/v1/mcp/spawn")
        assert resp.json()["already_running"] is True

    def test_mcp_kill_returns_killed_true_when_running(self, client: TestClient) -> None:
        with patch("neuralcleave.mcp.spawn.MCP_PROCESS") as mock_proc:
            mock_proc.kill.return_value = True
            resp = client.delete("/api/v1/mcp/server")
        assert resp.status_code == 200
        assert resp.json()["killed"] is True

    def test_mcp_kill_returns_killed_false_when_not_running(self, client: TestClient) -> None:
        with patch("neuralcleave.mcp.spawn.MCP_PROCESS") as mock_proc:
            mock_proc.kill.return_value = False
            resp = client.delete("/api/v1/mcp/server")
        assert resp.json()["killed"] is False
