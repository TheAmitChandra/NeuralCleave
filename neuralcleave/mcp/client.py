"""MCP stdio client — connects out to an external MCP server subprocess.

Mirrors the JSON-RPC 2.0 newline-delimited protocol :class:`McpServer`
implements, but from the other side: NeuralCleave spawns someone else's MCP
server (a company's internal-tools server, another agent's server, ...) as a
subprocess, performs the ``initialize`` handshake, discovers its tools via
``tools/list``, and can then invoke them via ``tools/call``.

This is the missing half of MCP support — :class:`McpServer` already lets
external clients (Claude Code, Cursor) call into NeuralCleave; McpClient lets
NeuralCleave call out to them.

Usage::

    client = McpClient(["python", "-m", "some_mcp_server"])
    await client.connect()
    tools = await client.list_tools()
    content = await client.call_tool(tools[0].name, {"arg": "value"})
    await client.close()
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Any

from neuralcleave.mcp.protocol import MCP_PROTOCOL_VERSION, JsonRpcRequest, McpContent, McpToolDescriptor

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 30.0
_CLIENT_NAME = "neuralcleave"
_CLIENT_VERSION = "2.1.5"


class McpClientError(Exception):
    """Raised when an external MCP server returns a JSON-RPC error, or the connection fails."""


class McpClient:
    """Connects to one external MCP stdio server as a subprocess.

    Args:
        command: argv to spawn the external server, e.g. ``["python", "-m", "some_server"]``.
        timeout: seconds to wait for a response before raising :class:`McpClientError`.
    """

    def __init__(self, command: list[str], *, timeout: float = _DEFAULT_TIMEOUT_S) -> None:
        self._command = command
        self._timeout = timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: "asyncio.Task[None] | None" = None
        self._pending: dict[int, "asyncio.Future[Any]"] = {}
        self._id_counter = itertools.count(1)
        self.server_info: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> dict[str, Any]:
        """Spawn the subprocess and perform the MCP initialize handshake.

        Returns the server's ``initialize`` result (protocolVersion,
        capabilities, serverInfo).
        """
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

        result = await self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": _CLIENT_NAME, "version": _CLIENT_VERSION},
            },
        )
        self.server_info = result.get("serverInfo", {}) if isinstance(result, dict) else {}
        await self._notify("notifications/initialized")
        return result

    async def close(self) -> None:
        """Terminate the subprocess and cancel the reader task. Safe to call more than once."""
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None

        if self._proc is not None:
            if self._proc.returncode is None:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._proc.kill()
            self._proc = None

        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    # ── MCP methods ───────────────────────────────────────────────────────────

    async def list_tools(self) -> list[McpToolDescriptor]:
        """Return every tool the external server advertises via ``tools/list``."""
        result = await self._request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return [
            McpToolDescriptor(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> list[McpContent]:
        """Invoke a tool on the external server via ``tools/call``."""
        result = await self._request("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content", []) if isinstance(result, dict) else []
        return [McpContent(type=c.get("type", "text"), text=c.get("text", "")) for c in content]

    # ── JSON-RPC transport ───────────────────────────────────────────────────────

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                self._handle_line(line)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("mcp.client read loop error: %s", exc)

    def _handle_line(self, line: bytes) -> None:
        raw = line.strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("mcp.client: non-JSON line from server: %r", raw[:200])
            return

        msg_id = data.get("id")
        if msg_id is None:
            return  # notification from the server — nothing to resolve

        fut = self._pending.pop(msg_id, None)
        if fut is None or fut.done():
            return
        if "error" in data:
            err = data["error"] or {}
            fut.set_exception(
                McpClientError(f"{err.get('message', 'MCP error')} (code {err.get('code')})")
            )
        else:
            fut.set_result(data.get("result"))

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        if self._proc is None or self._proc.stdin is None:
            raise McpClientError("not connected")

        req_id = next(self._id_counter)
        req = JsonRpcRequest(method=method, id=req_id, params=params)
        fut: "asyncio.Future[Any]" = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut

        line = json.dumps(req.to_dict(), separators=(",", ":")) + "\n"
        self._proc.stdin.write(line.encode())
        await self._proc.stdin.drain()

        try:
            return await asyncio.wait_for(fut, timeout=self._timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise McpClientError(f"timed out waiting for response to {method!r}") from None

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        req = JsonRpcRequest(method=method, params=params)
        line = json.dumps(req.to_dict(), separators=(",", ":")) + "\n"
        self._proc.stdin.write(line.encode())
        await self._proc.stdin.drain()
