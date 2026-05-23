"""Unit tests for the MCP (Model Context Protocol) server endpoint.

Tests cover:
    POST /mcp/
        initialize          — capabilities handshake (no auth)
        tools/list          — returns registered tools in MCP schema (no auth)
        tools/call          — executes tool (requires Bearer token)
        tools/call missing name   — 422-style JSON-RPC error
        tools/call no auth        — auth-required error
        tools/call unknown tool   — tool-not-found error
        unknown method            — method-not-found error
        malformed JSON            — parse error
        missing jsonrpc field     — invalid-request error

    GET /mcp/info
        returns server name, version, tool count, tool names
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.mcp import router, _registry, SERVER_NAME, SERVER_VERSION, MCP_PROTOCOL_VERSION
from app.core.tools.registry import ToolDefinition, ToolCallResult


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_app() -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.include_router(router)
    return app, TestClient(app, raise_server_exceptions=False)


def _rpc(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


_FAKE_USER_ID = str(uuid.uuid4())
_BEARER = "Bearer test-token-abc"


# ---------------------------------------------------------------------------
# Tests — initialize
# ---------------------------------------------------------------------------

class TestInitialize:
    def test_returns_200(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("initialize"))
        assert resp.status_code == 200

    def test_result_contains_protocol_version(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("initialize"))
        result = resp.json()["result"]
        assert result["protocolVersion"] == MCP_PROTOCOL_VERSION

    def test_result_contains_server_info(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("initialize"))
        result = resp.json()["result"]
        assert result["serverInfo"]["name"] == SERVER_NAME
        assert result["serverInfo"]["version"] == SERVER_VERSION

    def test_result_has_tools_capability(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("initialize"))
        result = resp.json()["result"]
        assert "tools" in result["capabilities"]

    def test_jsonrpc_envelope_correct(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("initialize", req_id=42))
        body = resp.json()
        assert body["jsonrpc"] == "2.0"
        assert body["id"] == 42
        assert "result" in body
        assert "error" not in body


# ---------------------------------------------------------------------------
# Tests — tools/list
# ---------------------------------------------------------------------------

class TestToolsList:
    def test_returns_200(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("tools/list"))
        assert resp.status_code == 200

    def test_result_has_tools_array(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("tools/list"))
        result = resp.json()["result"]
        assert "tools" in result
        assert isinstance(result["tools"], list)

    def test_each_tool_has_required_mcp_fields(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("tools/list"))
        tools = resp.json()["result"]["tools"]
        # Registry has default tools — we just need at least one
        if tools:
            tool = tools[0]
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    def test_no_auth_required(self):
        """tools/list should work without Authorization header."""
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("tools/list"))
        assert "error" not in resp.json()


# ---------------------------------------------------------------------------
# Tests — tools/call
# ---------------------------------------------------------------------------

class TestToolsCall:
    def test_requires_auth(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("tools/call", {"name": "file.read", "arguments": {}}))
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32000  # _ERR_AUTH_REQUIRED

    def test_unknown_tool_returns_tool_not_found(self, monkeypatch):
        _, client = _make_app()
        monkeypatch.setattr(
            "app.api.v1.mcp._extract_bearer_user_id",
            lambda _: uuid.UUID(_FAKE_USER_ID),
        )
        resp = client.post(
            "/mcp/",
            json=_rpc("tools/call", {"name": "nonexistent.tool", "arguments": {}}),
            headers={"Authorization": _BEARER},
        )
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32001  # _ERR_TOOL_NOT_FOUND

    def test_missing_name_param_returns_invalid_params(self, monkeypatch):
        _, client = _make_app()
        monkeypatch.setattr(
            "app.api.v1.mcp._extract_bearer_user_id",
            lambda _: uuid.UUID(_FAKE_USER_ID),
        )
        resp = client.post(
            "/mcp/",
            json=_rpc("tools/call", {"arguments": {}}),  # missing "name"
            headers={"Authorization": _BEARER},
        )
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32602  # _ERR_INVALID_PARAMS

    def test_successful_call_returns_content_array(self, monkeypatch):
        _, client = _make_app()
        monkeypatch.setattr(
            "app.api.v1.mcp._extract_bearer_user_id",
            lambda _: uuid.UUID(_FAKE_USER_ID),
        )
        from app.core.tools.registry import ToolDefinition
        fake_def = ToolDefinition(
            name="file.read",
            description="Read a file",
            permissions=["file_read"],
            risk_level="low",
        )
        monkeypatch.setattr(_registry, "get_definition", lambda _name: fake_def)
        fake_result = ToolCallResult(
            tool_name="file.read",
            agent_id=uuid.UUID(_FAKE_USER_ID),
            success=True,
            output="file contents here",
            requires_approval=False,
        )
        async def _fake_execute(_req):
            return fake_result

        monkeypatch.setattr(_registry, "execute", _fake_execute)

        resp = client.post(
            "/mcp/",
            json=_rpc("tools/call", {"name": "file.read", "arguments": {"path": "/tmp/x"}}),
            headers={"Authorization": _BEARER},
        )
        body = resp.json()
        assert "result" in body
        result = body["result"]
        assert "content" in result
        assert result["content"][0]["type"] == "text"
        assert result["isError"] is False

    def test_failed_tool_sets_is_error_true(self, monkeypatch):
        _, client = _make_app()
        monkeypatch.setattr(
            "app.api.v1.mcp._extract_bearer_user_id",
            lambda _: uuid.UUID(_FAKE_USER_ID),
        )
        from app.core.tools.registry import ToolDefinition
        fake_def = ToolDefinition(
            name="file.read",
            description="Read a file",
            permissions=["file_read"],
            risk_level="low",
        )
        monkeypatch.setattr(_registry, "get_definition", lambda _name: fake_def)
        fake_result = ToolCallResult(
            tool_name="file.read",
            agent_id=uuid.UUID(_FAKE_USER_ID),
            success=False,
            error="Permission denied",
            requires_approval=False,
        )
        async def _fake_execute(_req):
            return fake_result

        monkeypatch.setattr(_registry, "execute", _fake_execute)

        resp = client.post(
            "/mcp/",
            json=_rpc("tools/call", {"name": "file.read", "arguments": {}}),
            headers={"Authorization": _BEARER},
        )
        body = resp.json()
        assert body["result"]["isError"] is True

    def test_requires_approval_tool_returns_approval_message(self, monkeypatch):
        _, client = _make_app()
        monkeypatch.setattr(
            "app.api.v1.mcp._extract_bearer_user_id",
            lambda _: uuid.UUID(_FAKE_USER_ID),
        )
        from app.core.tools.registry import ToolDefinition
        fake_def = ToolDefinition(
            name="shell.execute",
            description="Execute shell command",
            permissions=["shell_access"],
            risk_level="high",
            requires_approval=True,
        )
        monkeypatch.setattr(_registry, "get_definition", lambda _name: fake_def)
        fake_result = ToolCallResult(
            tool_name="shell.execute",
            agent_id=uuid.UUID(_FAKE_USER_ID),
            success=False,
            requires_approval=True,
        )
        async def _fake_execute(_req):
            return fake_result

        monkeypatch.setattr(_registry, "execute", _fake_execute)

        resp = client.post(
            "/mcp/",
            json=_rpc("tools/call", {"name": "shell.execute", "arguments": {}}),
            headers={"Authorization": _BEARER},
        )
        body = resp.json()
        assert "result" in body
        assert body["result"]["metadata"]["requires_approval"] is True


# ---------------------------------------------------------------------------
# Tests — protocol errors
# ---------------------------------------------------------------------------

class TestProtocolErrors:
    def test_unknown_method_returns_method_not_found(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=_rpc("no.such.method"))
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32601

    def test_malformed_json_returns_parse_error(self):
        _, client = _make_app()
        resp = client.post(
            "/mcp/",
            content=b"not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32700

    def test_missing_jsonrpc_field_returns_invalid_request(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json={"method": "initialize"})  # no jsonrpc field
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32600

    def test_array_body_returns_invalid_request(self):
        _, client = _make_app()
        resp = client.post("/mcp/", json=[{"jsonrpc": "2.0", "method": "initialize"}])
        body = resp.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# Tests — GET /mcp/info
# ---------------------------------------------------------------------------

class TestMcpInfo:
    def test_returns_200(self):
        _, client = _make_app()
        resp = client.get("/mcp/info")
        assert resp.status_code == 200

    def test_contains_server_name(self):
        _, client = _make_app()
        resp = client.get("/mcp/info")
        assert resp.json()["server"] == SERVER_NAME

    def test_contains_tool_count(self):
        _, client = _make_app()
        resp = client.get("/mcp/info")
        body = resp.json()
        assert "tool_count" in body
        assert isinstance(body["tool_count"], int)

    def test_tools_list_matches_tool_count(self):
        _, client = _make_app()
        resp = client.get("/mcp/info")
        body = resp.json()
        assert len(body["tools"]) == body["tool_count"]
