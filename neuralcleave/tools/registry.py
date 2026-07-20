"""Tool registry — discover, register, and dispatch tool calls.

The registry is the single point of contact between the agent pipeline and
individual tools.  It:
  - Holds a name → Tool instance mapping
  - Validates tool call arguments before dispatch
  - Enforces permission checks
  - Converts results to prompt-injectable strings
  - Provides schema export for LLM function-calling payloads

Usage::

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(FileOpsTool())

    # Dispatch from the pipeline
    result = await registry.call("web_search", {"query": "Python asyncio"})
    print(result.to_prompt_block())

    # Export all schemas for the LLM system prompt
    schemas = registry.all_schemas()
"""

from __future__ import annotations

import logging
from typing import Any

from cortexflow_ai.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

# Permissions that are always allowed (no explicit grant needed)
_SAFE_PERMISSIONS: set[str] = set()


class PermissionDeniedError(Exception):
    """Raised when a tool requires permissions not in the allowed set."""


class ToolNotFoundError(KeyError):
    """Raised when the requested tool name is not registered."""


class ToolRegistry:
    """Central registry for all agent tools.

    Args:
        allowed_permissions: Set of permission strings the runtime grants.
                             Default grants all permissions (personal use — no
                             RBAC needed). Pass an explicit set to restrict.
    """

    def __init__(
        self,
        allowed_permissions: set[str] | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        # None = grant everything; explicit set = whitelist
        self._allowed: set[str] | None = allowed_permissions

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """Register a tool instance. Overwrites any existing tool with the same name."""
        self._tools[tool.name] = tool
        logger.debug("tool.registered name=%s permissions=%s", tool.name, tool.permissions)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        check_permissions: bool = True,
    ) -> ToolResult:
        """Execute a registered tool by name.

        Args:
            tool_name:         Name of the tool to invoke.
            arguments:         Dict of keyword arguments for the tool.
            check_permissions: If True (default), enforce permission whitelist.

        Returns:
            ToolResult — never raises; errors are wrapped in ToolResult.error.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                tool=tool_name,
                output=None,
                error=f"Tool {tool_name!r} not found. Available: {', '.join(self.names)}",
            )

        if check_permissions and self._allowed is not None:
            denied = [p for p in tool.permissions if p not in self._allowed and p not in _SAFE_PERMISSIONS]
            if denied:
                return ToolResult(
                    tool=tool_name,
                    output=None,
                    error=f"Permission denied: {tool_name!r} requires {denied}",
                )

        try:
            result = await tool.execute(**arguments)
            logger.info(
                "tool.call name=%s success=%s", tool_name, result.success
            )
            return result
        except Exception as exc:
            logger.error("tool.call name=%s unhandled error: %s", tool_name, exc)
            return ToolResult(tool=tool_name, output=None, error=str(exc))

    # ------------------------------------------------------------------
    # Schema export
    # ------------------------------------------------------------------

    def all_schemas(self) -> list[dict[str, Any]]:
        """Export all tool schemas for LLM function-calling prompt injection."""
        return [tool.get_schema() for tool in self._tools.values()]

    def tools_prompt_block(self) -> str:
        """Return a compact tool catalogue for injection into the system prompt."""
        if not self._tools:
            return "No tools available."
        lines = ["Available tools:"]
        for name, tool in sorted(self._tools.items()):
            lines.append(f"  {name}: {tool.description}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Convenience: build the default registry with all built-in tools
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "ToolRegistry":
        """Return a registry pre-loaded with all built-in tools."""
        from cortexflow_ai.tools.file_ops import FileOpsTool
        from cortexflow_ai.tools.shell import ShellTool
        from cortexflow_ai.tools.web_search import WebSearchTool

        registry = cls()
        registry.register(WebSearchTool())
        registry.register(FileOpsTool())
        registry.register(ShellTool())
        return registry
