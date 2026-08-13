"""Adapts one external MCP tool (discovered via McpClient) into a NeuralCleave Tool.

Lets tools exposed by an external MCP server (a company's internal-tools
server, another agent's server, ...) be registered into the same
ToolRegistry the pipeline's tool-calling loop already uses — once
registered, an external MCP tool is indistinguishable from a built-in one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neuralcleave.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    from neuralcleave.mcp.client import McpClient
    from neuralcleave.mcp.protocol import McpToolDescriptor

# MCP JSON Schema "type" -> NeuralCleave Tool.parameters "type" string.
_JSON_TO_PY_TYPE = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def schema_to_parameters(input_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Convert an MCP ``inputSchema`` (JSON Schema) into NeuralCleave's parameter dict shape."""
    if not isinstance(input_schema, dict):
        return {}
    props = input_schema.get("properties", {})
    if not isinstance(props, dict):
        return {}
    required = set(input_schema.get("required", []))
    return {
        name: {
            "type": _JSON_TO_PY_TYPE.get(spec.get("type", "string"), "str"),
            "description": spec.get("description", ""),
            "required": name in required,
        }
        for name, spec in props.items()
        if isinstance(spec, dict)
    }


class McpClientTool(Tool):
    """Wraps one tool from an external MCP server as a local Tool.

    Args:
        client:      The connected McpClient owning this tool.
        descriptor:  The tool's MCP descriptor (name/description/inputSchema).
        server_name: Short identifier for the external server, used to
                     namespace the local tool name and avoid collisions with
                     built-in tools or other connected MCP servers. The
                     registered name is ``mcp_{server_name}_{tool_name}``.
    """

    permissions: list[str] = ["network"]

    def __init__(self, client: "McpClient", descriptor: "McpToolDescriptor", server_name: str) -> None:
        self._client = client
        self._remote_name = descriptor.name
        self.name = f"mcp_{server_name}_{descriptor.name}"
        self.description = (
            descriptor.description or f"External MCP tool {descriptor.name!r} from {server_name!r}."
        )
        self.parameters = schema_to_parameters(descriptor.input_schema)

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            content = await self._client.call_tool(self._remote_name, kwargs)
        except Exception as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        text = "\n".join(c.text for c in content if c.text)
        return ToolResult(tool=self.name, output=text)
