"""Adapts NeuralCleave's ToolRegistry to MCP tool descriptors and dispatches calls.

The adapter is the bridge between MCP's ``tools/list`` / ``tools/call`` methods
and the tool registry already used by ``CognitivePipeline``.

Tool parameter schemas are translated from NeuralCleave's internal format
(``tool.get_schema()``) directly — the JSON Schema shape is the same that MCP
expects in ``inputSchema``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neuralcleave.mcp.protocol import McpContent, McpToolDescriptor

if TYPE_CHECKING:
    from neuralcleave.tools.registry import ToolRegistry


class McpToolAdapter:
    """Wraps a :class:`ToolRegistry` and exposes it through the MCP protocol.

    Args:
        registry: The tool registry to expose. May be ``None``; in that case
                  ``list_tools`` returns an empty list and ``call_tool`` always
                  returns a not-found error block.
    """

    def __init__(self, registry: "ToolRegistry | None" = None) -> None:
        self._registry = registry

    # ── Tool discovery ────────────────────────────────────────────────────────

    def list_tools(self) -> list[McpToolDescriptor]:
        """Return all registered tools as MCP tool descriptors."""
        if self._registry is None:
            return []

        descriptors: list[McpToolDescriptor] = []
        for name in self._registry.names:
            tool = self._registry.get(name)
            if tool is None:
                continue
            schema = tool.get_schema()
            descriptors.append(
                McpToolDescriptor(
                    name=schema["name"],
                    description=schema["description"],
                    input_schema=schema.get("parameters", {"type": "object", "properties": {}}),
                )
            )
        return descriptors

    # ── Tool invocation ───────────────────────────────────────────────────────

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> list[McpContent]:
        """Invoke a tool by name and return MCP content blocks.

        Args:
            name:      Tool name matching a registered tool.
            arguments: Keyword arguments for the tool.  Defaults to ``{}``.

        Returns:
            A list of :class:`McpContent` items — always at least one.
        """
        if self._registry is None:
            return [McpContent(type="text", text="[ERROR] No tool registry is configured.")]

        args = arguments or {}
        result = await self._registry.call(name, args)

        if result.error:
            return [McpContent(type="text", text=f"[ERROR] {result.error}")]

        output_text = (
            str(result.output) if not isinstance(result.output, str) else result.output
        )
        return [McpContent(type="text", text=output_text)]

    # ── Schema helpers ────────────────────────────────────────────────────────

    def tools_list_result(self) -> dict[str, Any]:
        """Return the ``result`` payload for a ``tools/list`` response."""
        return {"tools": [t.to_dict() for t in self.list_tools()]}

    async def tools_call_result(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the ``result`` payload for a ``tools/call`` response."""
        content = await self.call_tool(name, arguments)
        return {"content": [c.to_dict() for c in content]}
