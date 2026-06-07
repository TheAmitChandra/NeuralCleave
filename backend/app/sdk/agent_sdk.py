"""CortexFlow Agent SDK — base class for custom agent plugins.

Plugin authors subclass :class:`AgentSDK` to create custom agent types that
integrate with the CortexFlow cognitive loop (plan → execute → validate →
reflect) without requiring access to internal AgentRuntime internals.

Architecture
────────────
    Plugin defines:   class MyAgent(AgentSDK): ...
    Framework calls:  on_start(), handle_task(), on_stop(), on_error()
    Agent SDK calls:  tool registry, memory, observability hooks

Lifecycle hooks
───────────────
    on_start()      Called once when the agent is first registered / activated.
    handle_task()   Called for each task dispatched to this agent type.
    on_stop()       Called on graceful shutdown.
    on_error()      Called when handle_task() raises an unhandled exception.

Usage::

    from app.sdk import AgentSDK
    from app.core.tools.registry import ToolRegistry, ToolCallRequest
    import uuid

    class SummaryAgent(AgentSDK):
        agent_type = "summary_agent"
        description = "Summarises documents using the LLM router"

        async def on_start(self) -> None:
            self.registry = ToolRegistry.get_instance()

        async def handle_task(self, task_payload: dict) -> dict:
            result = await self.call_tool("llm_complete", {
                "prompt": task_payload["text"],
                "max_tokens": 256,
            })
            return {"summary": result.output}

        async def on_stop(self) -> None:
            self.logger.info("summary_agent.stopped")

Register the custom agent type with the AgentRegistry::

    from app.sdk.agent_sdk import AgentRegistry

    AgentRegistry.register(SummaryAgent)
"""

from __future__ import annotations

import abc
import uuid
from typing import Any

from app.core.observability.logs import get_logger
from app.core.observability.tracing import traced_operation
from app.core.tools.registry import ToolCallRequest, ToolCallResult, ToolRegistry

# ---------------------------------------------------------------------------
# AgentRegistry — catalogue of plugin agent types
# ---------------------------------------------------------------------------


class AgentRegistry:
    """Global catalogue mapping ``agent_type`` strings to :class:`AgentSDK` classes.

    Plugin agents are registered here so the CortexFlow agent dispatch layer
    can instantiate the correct class when an agent of that type is created.

    Usage::

        AgentRegistry.register(MyAgent)
        klass = AgentRegistry.get("my_agent")
        instance = klass(agent_id="...", config={})
    """

    _registry: dict[str, type["AgentSDK"]] = {}

    @classmethod
    def register(cls, agent_class: type["AgentSDK"]) -> None:
        """Register an AgentSDK subclass."""
        if not agent_class.agent_type:
            raise ValueError(f"AgentSDK subclass '{agent_class.__name__}' must set agent_type")
        if agent_class.agent_type in cls._registry:
            raise ValueError(f"Agent type '{agent_class.agent_type}' is already registered")
        cls._registry[agent_class.agent_type] = agent_class
        _log = get_logger(__name__)
        _log.info("sdk.agent_type_registered", agent_type=agent_class.agent_type)

    @classmethod
    def get(cls, agent_type: str) -> "type[AgentSDK] | None":
        """Return the registered class for *agent_type*, or None."""
        return cls._registry.get(agent_type)

    @classmethod
    def list_types(cls) -> list[str]:
        """Return all registered agent type names."""
        return list(cls._registry.keys())

    @classmethod
    def unregister(cls, agent_type: str) -> None:
        """Remove an agent type (useful in tests)."""
        cls._registry.pop(agent_type, None)


# ---------------------------------------------------------------------------
# AgentSDK — base class for plugin agents
# ---------------------------------------------------------------------------


class AgentSDK(abc.ABC):
    """Base class for CortexFlow plugin agents.

    Subclass this, set :attr:`agent_type`, implement :meth:`handle_task`,
    and optionally override the lifecycle hooks.

    Class attributes
    ────────────────
    agent_type    Unique string identifier (e.g. ``"weather_agent"``).
                  This must match the ``agent_type`` field in AgentConfig.
    description   Human-readable description displayed in the UI.
    version       SemVer string for your plugin (e.g. ``"1.0.0"``).
    """

    agent_type: str = ""
    description: str = ""
    version: str = "0.1.0"

    def __init__(
        self,
        *,
        agent_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.config: dict[str, Any] = config or {}
        self.logger = get_logger(f"sdk.agent.{self.agent_type}")
        self._tool_registry: ToolRegistry = ToolRegistry.get_instance()

    # ------------------------------------------------------------------
    # Lifecycle hooks — override in subclass as needed
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        """Called once when the agent is first activated.

        Use this to open connections, warm up caches, or pre-load models.
        The default implementation is a no-op.
        """

    async def on_stop(self) -> None:
        """Called on graceful shutdown.

        Close connections, flush buffers, etc.
        The default implementation is a no-op.
        """

    async def on_error(self, task_payload: dict[str, Any], exc: Exception) -> None:
        """Called when :meth:`handle_task` raises an unhandled exception.

        The default implementation logs the error.  Override to add custom
        alerting or retry logic.
        """
        self.logger.error(
            "sdk.agent.task_error",
            agent_type=self.agent_type,
            agent_id=self.agent_id,
            error=str(exc),
        )

    # ------------------------------------------------------------------
    # Abstract — must be implemented by plugin authors
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def handle_task(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        """Process a single task dispatched to this agent.

        Parameters
        ----------
        task_payload:
            Arbitrary dict from the task submission. The schema is defined
            by the plugin — CortexFlow passes it through unchanged.

        Returns
        -------
        dict
            Task result stored in memory and returned to the caller.
        """

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> ToolCallResult:
        """Execute a registered tool through the full 9-step registry pipeline.

        Parameters
        ----------
        tool_name:
            Name of the tool to call (must be registered in the ToolRegistry).
        parameters:
            Tool-specific parameter dict (validated against tool's JSON schema).
        idempotency_key:
            Optional deduplication key — the registry will short-circuit and
            return the cached result if the same key was used before.

        Returns
        -------
        ToolCallResult
            Contains ``success``, ``output``, ``error``, ``execution_ms``, etc.
        """
        request = ToolCallRequest(
            tool_name=tool_name,
            agent_id=uuid.UUID(self.agent_id),
            parameters=parameters,
            idempotency_key=idempotency_key,
        )
        async with traced_operation(
            f"sdk.call_tool.{tool_name}",
            attributes={"agent_type": self.agent_type, "agent_id": self.agent_id},
        ):
            return await self._tool_registry.execute(request)

    async def dispatch(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        """Entry point called by the CortexFlow dispatch layer.

        Wraps :meth:`handle_task` with lifecycle and error handling.
        Plugin authors should NOT override this — override :meth:`handle_task`.
        """
        async with traced_operation(
            f"sdk.agent.dispatch",
            attributes={"agent_type": self.agent_type, "agent_id": self.agent_id},
        ):
            try:
                return await self.handle_task(task_payload)
            except Exception as exc:
                await self.on_error(task_payload, exc)
                return {"error": str(exc), "success": False}
