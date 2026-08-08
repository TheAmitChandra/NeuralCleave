"""Tests for McpToolAdapter.list_tools() and tools_list_result()."""

from __future__ import annotations

from neuralcleave.mcp.tool_adapter import McpToolAdapter
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _GreetTool(Tool):
    name = "greet"
    description = "Say hello."
    parameters = {"name": {"type": "str", "description": "Name to greet.", "required": True}}
    permissions: list[str] = []

    async def execute(self, name: str = "", **_) -> ToolResult:
        return ToolResult(tool=self.name, output=f"Hello, {name}!")


class _NoParamTool(Tool):
    name = "ping"
    description = "Check connectivity."
    parameters: dict = {}
    permissions: list[str] = []

    async def execute(self, **_) -> ToolResult:
        return ToolResult(tool=self.name, output="pong")


class TestMcpToolAdapterList:
    def _make_adapter(self, *tools: Tool) -> McpToolAdapter:
        registry = ToolRegistry()
        for t in tools:
            registry.register(t)
        return McpToolAdapter(registry)

    def test_empty_registry_returns_no_tools(self) -> None:
        adapter = McpToolAdapter(ToolRegistry())
        assert adapter.list_tools() == []

    def test_none_registry_returns_no_tools(self) -> None:
        adapter = McpToolAdapter(None)
        assert adapter.list_tools() == []

    def test_single_tool_returns_one_descriptor(self) -> None:
        adapter = self._make_adapter(_GreetTool())
        tools = adapter.list_tools()
        assert len(tools) == 1

    def test_tool_descriptor_has_correct_name(self) -> None:
        adapter = self._make_adapter(_GreetTool())
        assert adapter.list_tools()[0].name == "greet"

    def test_tool_descriptor_has_correct_description(self) -> None:
        adapter = self._make_adapter(_GreetTool())
        assert adapter.list_tools()[0].description == "Say hello."

    def test_tool_descriptor_has_input_schema(self) -> None:
        adapter = self._make_adapter(_GreetTool())
        schema = adapter.list_tools()[0].input_schema
        assert schema["type"] == "object"
        assert "name" in schema["properties"]

    def test_tool_with_no_params_has_empty_properties(self) -> None:
        adapter = self._make_adapter(_NoParamTool())
        schema = adapter.list_tools()[0].input_schema
        assert schema.get("properties", {}) == {}

    def test_tools_list_result_returns_tools_key(self) -> None:
        adapter = self._make_adapter(_GreetTool())
        result = adapter.tools_list_result()
        assert "tools" in result
        assert len(result["tools"]) == 1

    def test_tools_list_result_dicts_have_input_schema_key(self) -> None:
        adapter = self._make_adapter(_GreetTool())
        tool_dict = adapter.tools_list_result()["tools"][0]
        assert "inputSchema" in tool_dict
