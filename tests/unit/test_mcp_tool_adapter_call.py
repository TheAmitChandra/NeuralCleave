"""Tests for McpToolAdapter.call_tool() and tools_call_result()."""

from __future__ import annotations

import pytest

from neuralcleave.mcp.tool_adapter import McpToolAdapter
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echo text."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **_) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


class _FailTool(Tool):
    name = "fail"
    description = "Always fails."
    parameters: dict = {}
    permissions: list[str] = []

    async def execute(self, **_) -> ToolResult:
        return ToolResult(tool=self.name, output=None, error="intentional failure")


class TestMcpToolAdapterCall:
    def _make_adapter(self, *tools: Tool) -> McpToolAdapter:
        registry = ToolRegistry()
        for t in tools:
            registry.register(t)
        return McpToolAdapter(registry)

    @pytest.mark.asyncio
    async def test_call_tool_returns_text_content(self) -> None:
        adapter = self._make_adapter(_EchoTool())
        content = await adapter.call_tool("echo", {"text": "hello"})
        assert len(content) == 1
        assert content[0].type == "text"
        assert content[0].text == "hello"

    @pytest.mark.asyncio
    async def test_call_tool_unknown_returns_error_content(self) -> None:
        adapter = self._make_adapter(_EchoTool())
        content = await adapter.call_tool("nonexistent", {})
        assert content[0].type == "text"
        assert "ERROR" in content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_failure_returns_error_content(self) -> None:
        adapter = self._make_adapter(_FailTool())
        content = await adapter.call_tool("fail", {})
        assert "ERROR" in content[0].text
        assert "intentional failure" in content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_none_registry_returns_error(self) -> None:
        adapter = McpToolAdapter(None)
        content = await adapter.call_tool("echo", {})
        assert "ERROR" in content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_none_arguments_uses_empty_dict(self) -> None:
        adapter = self._make_adapter(_EchoTool())
        content = await adapter.call_tool("echo", None)
        assert content[0].type == "text"

    @pytest.mark.asyncio
    async def test_tools_call_result_returns_content_key(self) -> None:
        adapter = self._make_adapter(_EchoTool())
        result = await adapter.tools_call_result("echo", {"text": "hi"})
        assert "content" in result
        assert isinstance(result["content"], list)

    @pytest.mark.asyncio
    async def test_tools_call_result_content_has_type_and_text(self) -> None:
        adapter = self._make_adapter(_EchoTool())
        result = await adapter.tools_call_result("echo", {"text": "world"})
        item = result["content"][0]
        assert item["type"] == "text"
        assert item["text"] == "world"
