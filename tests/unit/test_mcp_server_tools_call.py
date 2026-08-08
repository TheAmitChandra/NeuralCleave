"""Tests for McpServer tools/call dispatch."""

from __future__ import annotations

import asyncio
import json

import pytest

from neuralcleave.mcp.server import McpServer
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echo text."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **_) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


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
async def test_tools_call_invokes_tool_and_returns_text() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    req = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "hello MCP"}},
    }) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=registry, reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    content = response["result"]["content"]
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "hello MCP"


@pytest.mark.asyncio
async def test_tools_call_unknown_tool_returns_error_content() -> None:
    registry = ToolRegistry()
    req = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "ghost_tool", "arguments": {}},
    }) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=registry, reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    content = response["result"]["content"]
    assert "ERROR" in content[0]["text"]


@pytest.mark.asyncio
async def test_tools_call_missing_name_param_returns_error() -> None:
    req = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"arguments": {}},
    }) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert "error" in response


@pytest.mark.asyncio
async def test_tools_call_response_id_matches_request() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    req = json.dumps({
        "jsonrpc": "2.0", "id": 42, "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "id-test"}},
    }) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=registry, reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert response["id"] == 42
