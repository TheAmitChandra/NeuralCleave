"""Tools API — list registered tools, retrieve schemas, and execute tools."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.tools import ToolExecuteRequest, ToolExecuteResponse, ToolListItem

from app.core.security.permission_engine import get_current_user
from app.core.tools.registry import ToolCallRequest, ToolCallResult, ToolDefinition, ToolRegistry
from app.db.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/tools")

# Process-level tool registry — use the singleton for the API layer
_registry = ToolRegistry.get_instance()


# ---------------------------------------------------------------------------
# Default tools registered at startup
# ---------------------------------------------------------------------------

# Stub handler: returns a not-implemented result for tools without a real impl
async def _stub_handler(params: dict) -> dict:
    return {"status": "not_implemented", "params": params}


_DEFAULT_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="file.read",
        description="Read the contents of a file within an allowed path scope.",
        permissions=["file_read"],
        risk_level="low",
    ),
    ToolDefinition(
        name="file.write",
        description="Write content to a file within an allowed path scope.",
        permissions=["file_write"],
        risk_level="medium",
        sandbox_required=True,
    ),
    ToolDefinition(
        name="shell.execute",
        description="Execute a command from the allowlist in a restricted shell.",
        permissions=["shell_access"],
        risk_level="high",
        requires_approval=True,
        sandbox_required=True,
    ),
    ToolDefinition(
        name="browser.navigate",
        description="Navigate a headless browser to a URL within allowed domains.",
        permissions=["web_access"],
        risk_level="medium",
        sandbox_required=True,
        allowed_domains=["*"],
    ),
    ToolDefinition(
        name="api.get",
        description="Perform an authenticated HTTP GET request to an external API.",
        permissions=["api_access"],
        risk_level="low",
    ),
    ToolDefinition(
        name="api.post",
        description="Perform an authenticated HTTP POST request to an external API.",
        permissions=["api_access"],
        risk_level="medium",
    ),
    ToolDefinition(
        name="db.query",
        description="Execute a read-only SQL query against the configured database.",
        permissions=["db_read"],
        risk_level="low",
    ),
    ToolDefinition(
        name="ml.infer",
        description="Run inference against a configured ML model endpoint.",
        permissions=["ml_access"],
        risk_level="low",
    ),
]


def _register_default_tools() -> None:
    """Register built-in tools into the singleton registry if not already present."""
    for tool in _DEFAULT_TOOLS:
        if _registry.get_definition(tool.name) is None:
            _registry.register(tool, _stub_handler)  # type: ignore[arg-type]


_register_default_tools()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[ToolListItem])
async def list_tools_endpoint(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List all registered tools."""
    tools = _registry.list_tools()
    return [
        {
            "name": t.name,
            "description": t.description,
            "risk_level": t.risk_level,
            "requires_approval": t.requires_approval,
            "permissions": t.permissions,
        }
        for t in tools
    ]


@router.get("/{tool_name}/schema")
async def get_tool_schema(
    tool_name: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the full schema for a registered tool."""
    tool = _registry.get_definition(tool_name)
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tool '{tool_name}' not found")
    return tool.model_dump()


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    body: ToolExecuteRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Execute a registered tool on behalf of an agent."""
    try:
        agent_uuid = uuid.UUID(body.agent_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid agent_id format")

    tool = _registry.get_definition(body.tool_name)
    if not tool:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tool '{body.tool_name}' not found")

    request = ToolCallRequest(
        tool_name=body.tool_name,
        agent_id=agent_uuid,
        parameters=body.parameters,
        idempotency_key=body.idempotency_key,
    )

    try:
        result: ToolCallResult = await _registry.execute(request)
    except Exception as exc:  # noqa: BLE001
        logger.error("tool_execution_error", tool=body.tool_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tool execution failed",
        )

    return {
        "tool_name": result.tool_name,
        "agent_id": str(result.agent_id),
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "risk_score": result.risk_score,
        "isolation_tier": result.isolation_tier,
        "execution_ms": result.execution_ms,
        "requires_approval": result.requires_approval,
    }
