"""Tests for McpServer tools/list method."""

from __future__ import annotations

import asyncio
import json

import pytest

from neuralcleave.mcp.server import McpServer
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _CountTool(Tool):
    name = "count"
    description = "Count things."
    parameters = {"n": {"type": "int", "description": "How many.", "required": True}}
    permissions: list[str] = []

    async def execute(self, n: int = 0, **_) -> ToolResult:
        return ToolResult(tool=self.name, output=str(n))


def _make_stream_pair(lines: list[bytes]):
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    reader.feed_eof()

    buf: list[bytes] = []

    class _FakeTransport(asyncio.BaseTransport):
        def write(self, data: bytes) -> None:
            buf.append(data)

        def is_closing(self) -> bool:
            return False

        def close(self) -> None:
            pass

        def get_extra_info(self, name, default=None):
            return default

    transport = _FakeTransport()
    protocol = asyncio.StreamReaderProtocol(reader)
    writer = asyncio.StreamWriter(transport, protocol, reader, asyncio.get_event_loop())
    writer._buf = buf  # type: ignore[attr-defined]
    return reader, writer


@pytest.mark.asyncio
async def test_tools_list_returns_empty_for_no_tools() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert response["result"]["tools"] == []


@pytest.mark.asyncio
async def test_tools_list_returns_registered_tool() -> None:
    registry = ToolRegistry()
    registry.register(_CountTool())
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=registry, reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    tools = response["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "count"


@pytest.mark.asyncio
async def test_tools_list_tool_has_input_schema() -> None:
    registry = ToolRegistry()
    registry.register(_CountTool())
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=registry, reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    tool = response["result"]["tools"][0]
    assert "inputSchema" in tool


@pytest.mark.asyncio
async def test_tools_list_response_id_matches() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/list"}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert response["id"] == 5
