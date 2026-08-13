"""Tests for McpClientTool — adapts an external MCP tool into a NeuralCleave Tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.mcp.client_tool import McpClientTool, schema_to_parameters
from neuralcleave.mcp.protocol import McpContent, McpToolDescriptor
from neuralcleave.tools.base import Tool


class TestSchemaToParameters:
    def test_converts_string_property(self) -> None:
        params = schema_to_parameters(
            {"type": "object", "properties": {"query": {"type": "string", "description": "The search query"}}}
        )
        assert params["query"]["type"] == "str"
        assert params["query"]["description"] == "The search query"

    def test_marks_required_fields(self) -> None:
        params = schema_to_parameters(
            {
                "type": "object",
                "properties": {"q": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["q"],
            }
        )
        assert params["q"]["required"] is True
        assert params["limit"]["required"] is False

    def test_maps_all_json_schema_types(self) -> None:
        params = schema_to_parameters(
            {
                "type": "object",
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "integer"},
                    "c": {"type": "number"},
                    "d": {"type": "boolean"},
                    "e": {"type": "array"},
                    "f": {"type": "object"},
                },
            }
        )
        assert params["a"]["type"] == "str"
        assert params["b"]["type"] == "int"
        assert params["c"]["type"] == "float"
        assert params["d"]["type"] == "bool"
        assert params["e"]["type"] == "list"
        assert params["f"]["type"] == "dict"

    def test_empty_schema_returns_empty_dict(self) -> None:
        assert schema_to_parameters({}) == {}

    def test_non_dict_schema_returns_empty_dict(self) -> None:
        assert schema_to_parameters(None) == {}  # type: ignore[arg-type]


def _descriptor(name="search", description="Search the web.", input_schema=None) -> McpToolDescriptor:
    return McpToolDescriptor(name=name, description=description, input_schema=input_schema or {})


class TestMcpClientTool:
    def test_is_a_tool(self) -> None:
        tool = McpClientTool(MagicMock(), _descriptor(), server_name="acme")
        assert isinstance(tool, Tool)

    def test_name_is_namespaced_by_server(self) -> None:
        tool = McpClientTool(MagicMock(), _descriptor(name="search"), server_name="acme")
        assert tool.name == "mcp_acme_search"

    def test_description_falls_back_when_empty(self) -> None:
        tool = McpClientTool(MagicMock(), _descriptor(description=""), server_name="acme")
        assert "search" in tool.description
        assert "acme" in tool.description

    def test_permissions_include_network(self) -> None:
        tool = McpClientTool(MagicMock(), _descriptor(), server_name="acme")
        assert "network" in tool.permissions

    def test_parameters_derived_from_input_schema(self) -> None:
        descriptor = _descriptor(
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
        )
        tool = McpClientTool(MagicMock(), descriptor, server_name="acme")
        assert tool.parameters["q"]["required"] is True

    @pytest.mark.asyncio
    async def test_execute_calls_client_with_remote_name_and_kwargs(self) -> None:
        client = MagicMock()
        client.call_tool = AsyncMock(return_value=[McpContent(type="text", text="ok")])
        tool = McpClientTool(client, _descriptor(name="search"), server_name="acme")

        await tool.execute(q="python")

        client.call_tool.assert_awaited_once_with("search", {"q": "python"})

    @pytest.mark.asyncio
    async def test_execute_joins_multiple_content_blocks(self) -> None:
        client = MagicMock()
        client.call_tool = AsyncMock(
            return_value=[McpContent(type="text", text="line one"), McpContent(type="text", text="line two")]
        )
        tool = McpClientTool(client, _descriptor(), server_name="acme")

        result = await tool.execute()

        assert result.output == "line one\nline two"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_wraps_client_exception_as_tool_error(self) -> None:
        client = MagicMock()
        client.call_tool = AsyncMock(side_effect=RuntimeError("connection lost"))
        tool = McpClientTool(client, _descriptor(), server_name="acme")

        result = await tool.execute()

        assert result.error == "connection lost"
        assert result.success is False
