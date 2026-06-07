"""MCP (Model Context Protocol) compatibility server.

Exposes CortexFlow tools to external AI clients via JSON-RPC 2.0 over HTTP.
Protocol: MCP 2024-11-05 — https://spec.modelcontextprotocol.io

Supported methods:
    initialize      — announce server capabilities (no auth required)
    tools/list      — list all registered tools in MCP inputSchema format
    tools/call      — execute a tool through the full ToolRegistry pipeline

Authentication:
    ``initialize`` and ``tools/list`` are public.
    ``tools/call`` requires an ``Authorization: Bearer <access-token>`` header.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Header
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.core.security.zero_trust import verify_access_token
from app.core.tools.registry import ToolCallRequest, ToolRegistry

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp"])

# Module-level singleton shared with the tools API
_registry = ToolRegistry.get_instance()

# Protocol constants
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "CortexFlow"
SERVER_VERSION = "1.0.0"

# Standard JSON-RPC 2.0 error codes
_ERR_PARSE = -32700
_ERR_INVALID_REQUEST = -32600
_ERR_METHOD_NOT_FOUND = -32601
_ERR_INVALID_PARAMS = -32602
_ERR_INTERNAL = -32603

# CortexFlow-specific MCP error codes
_ERR_AUTH_REQUIRED = -32000
_ERR_TOOL_NOT_FOUND = -32001


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ok(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_to_mcp_schema(tool) -> dict:
    """Convert a ToolDefinition to the MCP tools/list schema."""
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": {
            "type": "object",
            "properties": tool.parameters_schema.get("properties", {}),
            "required": tool.parameters_schema.get("required", []),
        },
    }


def _extract_bearer_user_id(authorization: str | None) -> uuid.UUID | None:
    """Parse Authorization header, verify JWT, return user UUID or None."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        subject = verify_access_token(parts[1])
        return uuid.UUID(subject)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# MCP JSON-RPC endpoint
# ---------------------------------------------------------------------------


@router.post("/")
async def mcp_handler(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """Handle MCP JSON-RPC 2.0 requests.

    All MCP traffic uses ``POST /mcp/``.  The ``method`` field in the body
    determines dispatch.  Responses always carry HTTP 200 — errors are
    expressed in the JSON-RPC ``error`` object per the MCP specification.
    """
    # --- Parse body ---
    try:
        body: Any = await request.json()
    except Exception:
        return JSONResponse(_err(None, _ERR_PARSE, "Parse error: body is not valid JSON"))

    if not isinstance(body, dict):
        return JSONResponse(_err(None, _ERR_INVALID_REQUEST, "Request must be a JSON object"))

    if body.get("jsonrpc") != "2.0" or "method" not in body:
        return JSONResponse(
            _err(body.get("id"), _ERR_INVALID_REQUEST, "Invalid JSON-RPC 2.0 request")
        )

    req_id = body.get("id")
    method: str = body["method"]
    params: dict = body.get("params") or {}

    logger.info("mcp_request", method=method, req_id=req_id)

    # ----------------------------------------------------------------
    # initialize — no auth required
    # ----------------------------------------------------------------
    if method == "initialize":
        return JSONResponse(
            _ok(
                req_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
        )

    # ----------------------------------------------------------------
    # tools/list — no auth required (read-only catalogue)
    # ----------------------------------------------------------------
    if method == "tools/list":
        mcp_tools = [_tool_to_mcp_schema(t) for t in _registry.list_tools()]
        return JSONResponse(_ok(req_id, {"tools": mcp_tools}))

    # ----------------------------------------------------------------
    # tools/call — auth required
    # ----------------------------------------------------------------
    if method == "tools/call":
        tool_name: str | None = params.get("name")
        arguments: dict = params.get("arguments") or {}

        if not tool_name:
            return JSONResponse(
                _err(req_id, _ERR_INVALID_PARAMS, "params.name is required for tools/call")
            )

        # Authenticate the caller
        user_id = _extract_bearer_user_id(authorization)
        if user_id is None:
            return JSONResponse(
                _err(
                    req_id,
                    _ERR_AUTH_REQUIRED,
                    "Authentication required: provide Authorization: Bearer <access-token>",
                )
            )

        # Validate tool exists
        tool_def = _registry.get_definition(tool_name)
        if tool_def is None:
            return JSONResponse(_err(req_id, _ERR_TOOL_NOT_FOUND, f"Tool not found: {tool_name!r}"))

        # Execute via the full 9-step ToolRegistry pipeline
        call = ToolCallRequest(
            tool_name=tool_name,
            agent_id=user_id,
            parameters=arguments,
        )
        try:
            result = await _registry.execute(call)
        except Exception as exc:
            logger.exception("mcp_tool_execution_error", tool=tool_name, error=str(exc))
            return JSONResponse(_err(req_id, _ERR_INTERNAL, "Internal error during tool execution"))

        # Tool blocked pending human approval
        if result.requires_approval:
            return JSONResponse(
                _ok(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Tool '{tool_name}' requires human approval before "
                                    "execution. An approval request has been queued."
                                ),
                            }
                        ],
                        "isError": False,
                        "metadata": {"requires_approval": True, "tool": tool_name},
                    },
                )
            )

        content_text = (
            str(result.output) if result.success else (result.error or "Tool execution failed")
        )
        return JSONResponse(
            _ok(
                req_id,
                {
                    "content": [{"type": "text", "text": content_text}],
                    "isError": not result.success,
                },
            )
        )

    # ----------------------------------------------------------------
    # Unknown method
    # ----------------------------------------------------------------
    return JSONResponse(_err(req_id, _ERR_METHOD_NOT_FOUND, f"Method not found: {method!r}"))


# ---------------------------------------------------------------------------
# Discovery endpoint — human-readable server info (no auth)
# ---------------------------------------------------------------------------


@router.get("/info")
async def mcp_info() -> dict:
    """Return MCP server metadata for discovery / health checks."""
    tools = _registry.list_tools()
    return {
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "protocol": MCP_PROTOCOL_VERSION,
        "tool_count": len(tools),
        "tools": [t.name for t in tools],
    }
