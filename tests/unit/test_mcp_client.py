"""Tests for McpClient — the outbound MCP client that connects to external MCP servers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.mcp.client import McpClient, McpClientError


class _FakeStdout:
    """Yields lines only once they've been pushed by a matching stdin write —
    mirrors real subprocess ordering (a response can't arrive before its
    request was sent), unlike a plain pre-queued list which would let later
    canned responses leak out before the client has even issued the request
    they answer."""

    def __init__(self, queue: "asyncio.Queue[bytes]"):
        self._queue = queue

    async def readline(self) -> bytes:
        return await self._queue.get()


class _FakeStdin:
    def __init__(self, on_write):
        self.written: list[dict] = []
        self._on_write = on_write

    def write(self, data: bytes) -> None:
        payload = json.loads(data.decode().strip())
        self.written.append(payload)
        self._on_write(payload)

    async def drain(self) -> None:
        return None


class _FakeProcess:
    """Each canned response in *stdout_lines* is released in order, one per
    outgoing request (writes without an "id" — notifications — release
    nothing, matching real MCP servers which don't reply to them)."""

    def __init__(self, stdout_lines: list[bytes]):
        self._response_queue = list(stdout_lines)
        self._stdout_ready: "asyncio.Queue[bytes]" = asyncio.Queue()
        self.stdin = _FakeStdin(on_write=self._on_write)
        self.stdout = _FakeStdout(self._stdout_ready)
        self.stderr = None
        self.returncode = None

    def _on_write(self, payload: dict) -> None:
        if "id" in payload and self._response_queue:
            self._stdout_ready.put_nowait(self._response_queue.pop(0))

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


def _line(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode()


def _init_response(msg_id: int = 1) -> bytes:
    return _line(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "some-server", "version": "1.0.0"},
            },
        }
    )


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_performs_initialize_handshake(self) -> None:
        proc = _FakeProcess([_init_response(1)])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake", "server"])
            result = await client.connect()

        assert result["serverInfo"]["name"] == "some-server"
        assert client.server_info["name"] == "some-server"
        await client.close()

    @pytest.mark.asyncio
    async def test_connect_sends_initialize_request_with_client_info(self) -> None:
        proc = _FakeProcess([_init_response(1)])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()

        first_write = proc.stdin.written[0]
        assert first_write["method"] == "initialize"
        assert first_write["params"]["clientInfo"]["name"] == "neuralcleave"
        await client.close()

    @pytest.mark.asyncio
    async def test_connect_sends_initialized_notification_after_handshake(self) -> None:
        proc = _FakeProcess([_init_response(1)])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()

        second_write = proc.stdin.written[1]
        assert second_write["method"] == "notifications/initialized"
        assert "id" not in second_write
        await client.close()

    @pytest.mark.asyncio
    async def test_is_connected_true_after_connect(self) -> None:
        proc = _FakeProcess([_init_response(1)])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            assert client.is_connected is False
            await client.connect()
            assert client.is_connected is True
        await client.close()


class TestListTools:
    @pytest.mark.asyncio
    async def test_list_tools_returns_descriptors(self) -> None:
        tools_response = _line(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search the web.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"q": {"type": "string"}},
                            },
                        }
                    ]
                },
            }
        )
        proc = _FakeProcess([_init_response(1), tools_response])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()
            tools = await client.list_tools()

        assert len(tools) == 1
        assert tools[0].name == "search"
        assert tools[0].description == "Search the web."
        assert tools[0].input_schema["properties"]["q"]["type"] == "string"
        await client.close()


class TestCallTool:
    @pytest.mark.asyncio
    async def test_call_tool_returns_content_blocks(self) -> None:
        call_response = _line(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"content": [{"type": "text", "text": "42 results found"}]},
            }
        )
        proc = _FakeProcess([_init_response(1), call_response])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()
            content = await client.call_tool("search", {"q": "python"})

        assert len(content) == 1
        assert content[0].text == "42 results found"
        await client.close()

    @pytest.mark.asyncio
    async def test_call_tool_sends_name_and_arguments(self) -> None:
        call_response = _line({"jsonrpc": "2.0", "id": 2, "result": {"content": []}})
        proc = _FakeProcess([_init_response(1), call_response])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()
            await client.call_tool("search", {"q": "python"})

        call_write = proc.stdin.written[-1]
        assert call_write["params"]["name"] == "search"
        assert call_write["params"]["arguments"] == {"q": "python"}
        await client.close()


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_server_error_response_raises_mcp_client_error(self) -> None:
        error_response = _line(
            {"jsonrpc": "2.0", "id": 2, "error": {"code": -32601, "message": "Method not found"}}
        )
        proc = _FakeProcess([_init_response(1), error_response])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()
            with pytest.raises(McpClientError, match="Method not found"):
                await client.list_tools()
        await client.close()

    @pytest.mark.asyncio
    async def test_request_before_connect_raises(self) -> None:
        client = McpClient(["fake"])
        with pytest.raises(McpClientError, match="not connected"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_request_times_out(self) -> None:
        proc = _FakeProcess([_init_response(1)])  # no response queued for the next call
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"], timeout=0.05)
            await client.connect()
            with pytest.raises(McpClientError, match="timed out"):
                await client.list_tools()
        await client.close()


class TestClose:
    @pytest.mark.asyncio
    async def test_close_terminates_process(self) -> None:
        proc = _FakeProcess([_init_response(1)])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()
            await client.close()

        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self) -> None:
        proc = _FakeProcess([_init_response(1)])
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            client = McpClient(["fake"])
            await client.connect()
            await client.close()
            await client.close()  # must not raise
