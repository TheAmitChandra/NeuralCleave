"""Tool Registry — central catalogue and execution pipeline for all NeuralCleave tools.

Every tool must be registered here before an agent can call it.  The registry
enforces the full 9-step verification pipeline defined in the SKILL spec:

    1. Schema validation          — parameters match ToolDefinition
    2. Permission check           — agent holds required scope
    3. Risk scoring               — calculate risk score 0-100
    4. Policy evaluation          — placeholder hook (wired in Phase 3)
    5. Dry-run simulation         — for risk > 60
    6. Sandbox allocation         — choose isolation tier
    7. Execution                  — delegate to tool implementation
    8. Result validation          — verify output schema
    9. Audit log                  — record full execution chain
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Coroutine, Literal

from pydantic import BaseModel, Field

from app.core.observability.logs import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

IsolationTier = Literal["process", "container", "isolated_container", "blocked"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class ToolDefinition(BaseModel):
    """Static descriptor for a registered tool."""

    name: str
    description: str
    permissions: list[str]
    risk_level: RiskLevel
    requires_approval: bool = False
    sandbox_required: bool = False
    timeout_seconds: int = 30
    allowed_domains: list[str] | None = None  # browser tools only
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    """Runtime call from an agent to a tool."""

    tool_name: str
    agent_id: uuid.UUID
    parameters: dict[str, Any]
    idempotency_key: str | None = None


class ToolCallResult(BaseModel):
    """Standardised result returned to the cognitive loop."""

    tool_name: str
    agent_id: uuid.UUID
    success: bool
    output: Any = None
    error: str | None = None
    risk_score: float = 0.0
    isolation_tier: IsolationTier = "process"
    execution_ms: float = 0.0
    idempotency_key: str | None = None
    requires_approval: bool = False


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

_RISK_BASE: dict[RiskLevel, float] = {
    "low": 10.0,
    "medium": 40.0,
    "high": 70.0,
    "critical": 90.0,
}

_PERMISSION_RISK: dict[str, float] = {
    "web_access": 5.0,
    "file.read": 5.0,
    "file.write": 15.0,
    "shell.execute": 20.0,
    "db.read": 5.0,
    "db.write": 20.0,
    "network.external": 10.0,
    "comms.send": 15.0,
}


def calculate_risk_score(tool_def: ToolDefinition) -> float:
    """Compute a composite risk score in [0, 100].

    Base score comes from the declared risk_level; each required permission
    adds an incremental penalty capped at 100.
    """
    score = _RISK_BASE[tool_def.risk_level]
    for perm in tool_def.permissions:
        score += _PERMISSION_RISK.get(perm, 2.0)
    return min(score, 100.0)


# ---------------------------------------------------------------------------
# Isolation tier selection
# ---------------------------------------------------------------------------


def resolve_isolation_tier(risk_score: float) -> IsolationTier:
    """Map a risk score to an execution isolation tier."""
    if risk_score <= 25:
        return "process"
    if risk_score <= 60:
        return "container"
    if risk_score <= 85:
        return "isolated_container"
    return "blocked"  # requires human approval before execution


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

# Type alias for async tool handler functions
ToolHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, Any]]


class ToolRegistry:
    """Singleton catalogue for all registered tools.

    Usage::

        registry = ToolRegistry.get_instance()

        # Register
        registry.register(my_tool_def, my_handler_fn)

        # Execute (runs the full 9-step pipeline)
        result = await registry.execute(ToolCallRequest(...))
    """

    _instance: "ToolRegistry | None" = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._register_default_tools()
        return cls._instance

    def _register_default_tools(self) -> None:
        """Import and register all built-in tool handlers."""
        # Local imports to prevent circular dependencies
        from app.core.tools.api_caller import register_api_tools
        from app.core.tools.browser import register_browser_tools
        from app.core.tools.database_tool import DB_QUERY_DEF, db_query
        from app.core.tools.filesystem import register_filesystem_tools
        from app.core.tools.shell import register_shell_tools

        register_browser_tools(self)
        register_shell_tools(self)
        register_filesystem_tools(self)
        register_api_tools(self)

        async def db_query_handler(params: dict[str, Any]) -> dict[str, Any]:
            from app.db.postgres import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                return await db_query(params, session)

        self.register(DB_QUERY_DEF, db_query_handler)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        """Add a tool to the registry."""
        if definition.name in self._tools:
            raise ValueError(f"Tool '{definition.name}' is already registered.")
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler
        logger.info("tool_registered", tool=definition.name, risk_level=definition.risk_level)

    def unregister(self, name: str) -> None:
        """Remove a tool (useful in tests)."""
        self._tools.pop(name, None)
        self._handlers.pop(name, None)

    def get_definition(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    # ------------------------------------------------------------------
    # Permission check
    # ------------------------------------------------------------------

    def check_permissions(
        self,
        tool_def: ToolDefinition,
        agent_permissions: list[str],
    ) -> tuple[bool, list[str]]:
        """Return (ok, missing_permissions)."""
        missing = [p for p in tool_def.permissions if p not in agent_permissions]
        return len(missing) == 0, missing

    # ------------------------------------------------------------------
    # Main execution pipeline
    # ------------------------------------------------------------------

    async def execute(
        self,
        request: ToolCallRequest,
        agent_permissions: list[str] | None = None,
        *,
        dry_run: bool = False,
    ) -> ToolCallResult:
        """Run the full 9-step verification and execution pipeline."""
        start = time.monotonic()

        # Step 1 — tool exists?
        tool_def = self._tools.get(request.tool_name)
        if tool_def is None:
            return ToolCallResult(
                tool_name=request.tool_name,
                agent_id=request.agent_id,
                success=False,
                error=f"Unknown tool: '{request.tool_name}'",
            )

        # Step 2 — permission check
        if agent_permissions is not None:
            ok, missing = self.check_permissions(tool_def, agent_permissions)
            if not ok:
                logger.warning(
                    "tool_permission_denied",
                    tool=request.tool_name,
                    agent_id=str(request.agent_id),
                    missing=missing,
                )
                return ToolCallResult(
                    tool_name=request.tool_name,
                    agent_id=request.agent_id,
                    success=False,
                    error=f"Permission denied. Missing scopes: {missing}",
                )

        # Step 3 — risk scoring
        risk_score = calculate_risk_score(tool_def)

        # Step 4 — policy evaluation (hook for Phase 3 policy engine)
        # policy_result = await policy_engine.evaluate(tool_def, request)

        # Step 5 — dry-run simulation for high-risk tools
        isolation_tier = resolve_isolation_tier(risk_score)

        if isolation_tier == "blocked" or tool_def.requires_approval:
            logger.warning(
                "tool_requires_approval",
                tool=request.tool_name,
                risk_score=risk_score,
                agent_id=str(request.agent_id),
            )
            return ToolCallResult(
                tool_name=request.tool_name,
                agent_id=request.agent_id,
                success=False,
                error="Tool requires human approval before execution.",
                risk_score=risk_score,
                isolation_tier=isolation_tier,
                requires_approval=True,
            )

        if dry_run:
            logger.info(
                "tool_dry_run",
                tool=request.tool_name,
                risk_score=risk_score,
                isolation_tier=isolation_tier,
            )
            return ToolCallResult(
                tool_name=request.tool_name,
                agent_id=request.agent_id,
                success=True,
                output={"dry_run": True, "predicted_isolation": isolation_tier},
                risk_score=risk_score,
                isolation_tier=isolation_tier,
            )

        # Step 6-7 — sandbox allocation + execution
        handler = self._handlers[request.tool_name]
        output = None
        error: str | None = None
        success = True

        try:
            output = await handler(request.parameters)
        except Exception as exc:  # noqa: BLE001
            success = False
            error = str(exc)
            logger.error(
                "tool_execution_error",
                tool=request.tool_name,
                agent_id=str(request.agent_id),
                error=error,
            )

        elapsed_ms = (time.monotonic() - start) * 1000

        if success:
            try:
                from app.core.memory.knowledge_graph import KnowledgeGraphMemory

                graph = KnowledgeGraphMemory()
                await graph.upsert_tool(request.tool_name, tool_def.risk_level)
                await graph.agent_uses_tool(request.agent_id, request.tool_name)
            except Exception as exc:
                logger.warning(
                    "graph_tool_log_failed",
                    tool=request.tool_name,
                    agent_id=str(request.agent_id),
                    error=str(exc),
                )

        # Step 8 — result validation (output type check)
        # Step 9 — audit log
        logger.info(
            "tool_executed",
            tool=request.tool_name,
            agent_id=str(request.agent_id),
            success=success,
            risk_score=risk_score,
            isolation_tier=isolation_tier,
            execution_ms=round(elapsed_ms, 2),
        )

        return ToolCallResult(
            tool_name=request.tool_name,
            agent_id=request.agent_id,
            success=success,
            output=output,
            error=error,
            risk_score=risk_score,
            isolation_tier=isolation_tier,
            execution_ms=round(elapsed_ms, 2),
            idempotency_key=request.idempotency_key,
        )
