"""Tests for McpServer edge cases: unknown method, parse error, notifications, ping."""

from __future__ import annotations

import asyncio
import json

import pytest

from neuralcleave.mcp.server import McpServer
from neuralcleave.tools.registry import ToolRegistry


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
async def test_unknown_method_returns_error_response() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "unknown/method"}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert "error" in response
    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_parse_error_returns_error_with_null_id() -> None:
    reader, writer = _make_stream_pair([b"not valid json\n"])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert response["error"]["code"] == -32700
    assert response["id"] is None


@pytest.mark.asyncio
async def test_notification_receives_no_response() -> None:
    notification = json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }) + "\n"
    reader, writer = _make_stream_pair([notification.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    assert output == b""


@pytest.mark.asyncio
async def test_ping_returns_empty_result() -> None:
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
    reader, writer = _make_stream_pair([req.encode()])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    response = json.loads(output.decode().strip())
    assert response["result"] == {}


@pytest.mark.asyncio
async def test_empty_line_produces_no_output() -> None:
    reader, writer = _make_stream_pair([b"\n"])

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf)  # type: ignore[attr-defined]
    assert output == b""


@pytest.mark.asyncio
async def test_multiple_requests_produce_multiple_responses() -> None:
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode() + b"\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode() + b"\n",
    ]
    reader, writer = _make_stream_pair(lines)

    server = McpServer(registry=ToolRegistry(), reader=reader, writer=writer)
    await server.run()

    output = b"".join(writer._buf).decode()  # type: ignore[attr-defined]
    responses = [json.loads(line) for line in output.strip().splitlines()]
    assert len(responses) == 2
    assert {r["id"] for r in responses} == {1, 2}
