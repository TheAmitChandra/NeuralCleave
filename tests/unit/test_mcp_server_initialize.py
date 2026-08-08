"""Tests for McpServer initialize handshake."""

from __future__ import annotations

import asyncio
import json

import pytest

from neuralcleave.mcp.protocol import MCP_PROTOCOL_VERSION
from neuralcleave.mcp.server import McpServer
from neuralcleave.tools.registry import ToolRegistry


def _make_stream_pair(
    lines: list[bytes],
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Build a reader pre-loaded with *lines* and a writer whose output is captured."""
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
async def test_initialize_returns_protocol_version() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert response["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_initialize_returns_tools_capability() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert "tools" in response["result"]["capabilities"]


@pytest.mark.asyncio
async def test_initialize_returns_server_info() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    server_info = response["result"]["serverInfo"]
    assert server_info["name"] == "neuralcleave"


@pytest.mark.asyncio
async def test_initialize_response_id_matches_request() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert response["id"] == 7
