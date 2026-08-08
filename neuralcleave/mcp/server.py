"""MCP stdio server — JSON-RPC 2.0 over stdin/stdout.

Reads newline-delimited JSON from stdin, dispatches to the appropriate handler,
and writes newline-delimited JSON responses to stdout.

The server is designed to be spawned as a subprocess by MCP clients (Claude Code,
Cursor, Codex). The client writes requests; this process reads them, calls the
appropriate NeuralCleave tool, and writes the response.

Usage::

    python -m neuralcleave.mcp.server

Or programmatically::

    from neuralcleave.mcp.server import McpServer
    from neuralcleave.tools.registry import ToolRegistry

    server = McpServer(registry=ToolRegistry.default())
    await server.run()

Protocol flow::

    client → {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
    server → {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"...","capabilities":{...}}}
    client → {"jsonrpc":"2.0","method":"notifications/initialized"}  (notification, no reply)
    client → {"jsonrpc":"2.0","id":2,"method":"tools/list"}
    server → {"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}
    client → {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"shell","arguments":{}}}
    server → {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"..."}]}}
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from neuralcleave.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCapabilities,
    McpServerInfo,
)
from neuralcleave.mcp.tool_adapter import McpToolAdapter

if TYPE_CHECKING:
    from neuralcleave.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class McpServer:
    """Newline-delimited JSON-RPC 2.0 server over asyncio streams.

    Args:
        registry:  Tool registry to expose as MCP tools.
        reader:    AsyncIO reader for incoming requests.  Defaults to stdin.
        writer:    AsyncIO writer for outgoing responses.  Defaults to stdout.
        server_info: Override the server identity block.
    """

    def __init__(
        self,
        registry: "ToolRegistry | None" = None,
        reader: asyncio.StreamReader | None = None,
        writer: asyncio.StreamWriter | None = None,
        server_info: McpServerInfo | None = None,
    ) -> None:
        self._adapter = McpToolAdapter(registry)
        self._reader = reader
        self._writer = writer
        self._info = server_info or McpServerInfo()
        self._initialized = False

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Read requests from the reader and write responses to the writer.

        Returns when stdin closes (EOF).
        """
        reader, writer = await self._open_streams()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                await self._handle_line(line, writer)
        finally:
            if writer and not writer.is_closing():
                writer.close()

    # ── Line dispatch ──────────────────────────────────────────────────────────

    async def _handle_line(self, line: bytes, writer: asyncio.StreamWriter) -> None:
        """Parse one line and write a response (unless it is a notification)."""
        raw = line.strip()
        if not raw:
            return

        # Parse JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            resp = JsonRpcResponse.err(None, PARSE_ERROR, f"Parse error: {exc}")
            await self._write(resp, writer)
            return

        # Parse request
        try:
            req = JsonRpcRequest.from_dict(data)
        except (ValueError, KeyError) as exc:
            resp = JsonRpcResponse.err(None, -32600, f"Invalid request: {exc}")
            await self._write(resp, writer)
            return

        # Notifications have no id — respond with nothing
        if req.is_notification:
            return

        resp = await self._dispatch(req)
        await self._write(resp, writer)

    # ── Method dispatch ────────────────────────────────────────────────────────

    async def _dispatch(self, req: JsonRpcRequest) -> JsonRpcResponse:
        method = req.method
        try:
            if method == "initialize":
                return await self._handle_initialize(req)
            if method == "tools/list":
                return self._handle_tools_list(req)
            if method == "tools/call":
                return await self._handle_tools_call(req)
            if method == "ping":
                return JsonRpcResponse.ok(req.id, {})
            return JsonRpcResponse.err(req.id, METHOD_NOT_FOUND, f"Method not found: {method!r}")
        except Exception as exc:
            logger.exception("mcp.server unhandled error in method %r", method)
            return JsonRpcResponse.err(req.id, INTERNAL_ERROR, f"Internal error: {exc}")

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_initialize(self, req: JsonRpcRequest) -> JsonRpcResponse:
        self._initialized = True
        return JsonRpcResponse.ok(
            req.id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": McpCapabilities().to_dict(),
                "serverInfo": self._info.to_dict(),
            },
        )

    def _handle_tools_list(self, req: JsonRpcRequest) -> JsonRpcResponse:
        return JsonRpcResponse.ok(req.id, self._adapter.tools_list_result())

    async def _handle_tools_call(self, req: JsonRpcRequest) -> JsonRpcResponse:
        params = req.params or {}
        name = params.get("name")
        if not name or not isinstance(name, str):
            return JsonRpcResponse.err(
                req.id, INVALID_PARAMS, "tools/call requires 'name' parameter"
            )
        arguments: dict[str, Any] = params.get("arguments") or {}
        result = await self._adapter.tools_call_result(name, arguments)
        return JsonRpcResponse.ok(req.id, result)

    # ── IO helpers ────────────────────────────────────────────────────────────

    async def _open_streams(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self._reader is not None and self._writer is not None:
            return self._reader, self._writer
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        w_transport, w_protocol = await loop.connect_write_pipe(
            asyncio.BaseProtocol, sys.stdout.buffer
        )
        writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)
        return reader, writer

    async def _write(self, resp: JsonRpcResponse, writer: asyncio.StreamWriter) -> None:
        line = json.dumps(resp.to_dict(), separators=(",", ":")) + "\n"
        writer.write(line.encode())
        await writer.drain()


# ── Entrypoint ────────────────────────────────────────────────────────────────


async def _main() -> None:
    from neuralcleave.tools.registry import ToolRegistry

    registry = ToolRegistry.default()
    server = McpServer(registry=registry)
    await server.run()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
