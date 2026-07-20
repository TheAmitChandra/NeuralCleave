"""NeuralCleave Tool SDK — base class and decorator for custom tool plugins.

Plugin authors subclass :class:`ToolSDK` or use the :func:`sdk_tool` decorator
to register new tools into the NeuralCleave tool registry without touching any
internal NeuralCleave code.

Architecture
────────────
                  ┌──────────────────────────┐
    Plugin file   │  @sdk_tool(...)           │
                  │  async def my_fn(p) → d  │
                  └────────────┬─────────────┘
                               │ register_tool()
                  ┌────────────▼─────────────┐
                  │    ToolRegistry          │  ← existing NeuralCleave singleton
                  │  (9-step exec pipeline)  │
                  └──────────────────────────┘

Usage — decorator style::

    from app.sdk import sdk_tool

    @sdk_tool(
        name="weather_lookup",
        description="Fetch current weather for a city",
        permissions=["network.external"],
        risk_level="low",
        parameters_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    async def weather_lookup(parameters: dict) -> dict:
        city = parameters["city"]
        # ... call weather API ...
        return {"temperature": 22, "unit": "C", "city": city}

Usage — class style (preferred for stateful tools)::

    from app.sdk import ToolSDK

    class WeatherTool(ToolSDK):
        name = "weather_lookup"
        description = "Fetch current weather for a city"
        permissions = ["network.external"]
        risk_level = "low"
        parameters_schema = {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        }

        async def run(self, parameters: dict) -> dict:
            ...
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Coroutine, Literal

from app.core.observability.logs import get_logger
from app.core.tools.registry import ToolDefinition, ToolRegistry

logger = get_logger(__name__)

RiskLevel = Literal["low", "medium", "high", "critical"]

# ---------------------------------------------------------------------------
# ToolSDK — base class for plugin tools
# ---------------------------------------------------------------------------


class ToolSDK:
    """Base class for NeuralCleave plugin tools.

    Subclass this, set the class-level attributes, and call
    :meth:`register` (or rely on auto-registration via :func:`register_tool`)
    to add your tool to the live registry.

    Class attributes
    ────────────────
    name                 Unique tool name — must be globally unique across all plugins.
    description          Human-readable description shown to agents and in the UI.
    permissions          List of permission strings (see ToolDefinition docs).
    risk_level           One of ``"low" | "medium" | "high" | "critical"``.
    requires_approval    If True, the registry will pause and await human approval.
    sandbox_required     If True, execution is isolated in a container sandbox.
    timeout_seconds      Maximum wall-clock execution time before the call is aborted.
    parameters_schema    JSON Schema dict describing expected parameters.
    """

    name: str = ""
    description: str = ""
    permissions: list[str] = []
    risk_level: RiskLevel = "low"
    requires_approval: bool = False
    sandbox_required: bool = False
    timeout_seconds: int = 30
    parameters_schema: dict[str, Any] = {}

    async def run(self, parameters: dict[str, Any]) -> Any:
        """Override this method with your tool logic.

        Parameters
        ----------
        parameters:
            Dict validated against :attr:`parameters_schema` by the registry.

        Returns
        -------
        Any JSON-serialisable value (dict, list, str, …).
        """
        raise NotImplementedError(f"{self.__class__.__name__}.run() not implemented")

    def _build_definition(self) -> ToolDefinition:
        if not self.name:
            raise ValueError(f"{self.__class__.__name__}.name must be set")
        return ToolDefinition(
            name=self.name,
            description=self.description,
            permissions=self.permissions,
            risk_level=self.risk_level,
            requires_approval=self.requires_approval,
            sandbox_required=self.sandbox_required,
            timeout_seconds=self.timeout_seconds,
            parameters_schema=self.parameters_schema,
        )

    def register(self, registry: ToolRegistry | None = None) -> None:
        """Register this tool in the global (or provided) ToolRegistry."""
        reg = registry or ToolRegistry.get_instance()
        definition = self._build_definition()
        # Bind to the async `run` method of this instance
        handler = self.run
        reg.register(definition, handler)
        logger.info("sdk.tool_registered", name=self.name, risk_level=self.risk_level)


# ---------------------------------------------------------------------------
# register_tool — imperative registration helper
# ---------------------------------------------------------------------------


def register_tool(
    handler: Callable[[dict[str, Any]], Coroutine[Any, Any, Any]],
    *,
    name: str,
    description: str,
    permissions: list[str],
    risk_level: RiskLevel = "low",
    requires_approval: bool = False,
    sandbox_required: bool = False,
    timeout_seconds: int = 30,
    parameters_schema: dict[str, Any] | None = None,
    registry: ToolRegistry | None = None,
) -> None:
    """Register an async function directly into the ToolRegistry.

    This is the functional twin of :class:`ToolSDK`. Prefer the decorator
    :func:`sdk_tool` for simple one-off tools.
    """
    definition = ToolDefinition(
        name=name,
        description=description,
        permissions=permissions,
        risk_level=risk_level,
        requires_approval=requires_approval,
        sandbox_required=sandbox_required,
        timeout_seconds=timeout_seconds,
        parameters_schema=parameters_schema or {},
    )
    reg = registry or ToolRegistry.get_instance()
    reg.register(definition, handler)
    logger.info("sdk.tool_registered", name=name, risk_level=risk_level)


# ---------------------------------------------------------------------------
# @sdk_tool — decorator
# ---------------------------------------------------------------------------


def sdk_tool(
    *,
    name: str,
    description: str,
    permissions: list[str],
    risk_level: RiskLevel = "low",
    requires_approval: bool = False,
    sandbox_required: bool = False,
    timeout_seconds: int = 30,
    parameters_schema: dict[str, Any] | None = None,
    registry: ToolRegistry | None = None,
) -> Callable:
    """Decorator that registers an async function as a NeuralCleave tool.

    The decorated function is returned unchanged (no wrapping), so it can
    also be called directly in tests without going through the registry.

    Example::

        @sdk_tool(
            name="echo",
            description="Returns the input unchanged",
            permissions=[],
            risk_level="low",
        )
        async def echo(parameters: dict) -> dict:
            return parameters
    """

    def decorator(fn: Callable) -> Callable:
        if not asyncio_is_coroutine(fn):
            raise TypeError(
                f"@sdk_tool: '{fn.__name__}' must be an async function "
                "(defined with 'async def')"
            )
        register_tool(
            fn,
            name=name,
            description=description,
            permissions=permissions,
            risk_level=risk_level,
            requires_approval=requires_approval,
            sandbox_required=sandbox_required,
            timeout_seconds=timeout_seconds,
            parameters_schema=parameters_schema,
            registry=registry,
        )

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await fn(*args, **kwargs)

        return wrapper

    return decorator


def asyncio_is_coroutine(fn: Callable) -> bool:
    """Return True if *fn* is defined as ``async def``."""
    import asyncio

    return asyncio.iscoroutinefunction(fn)
