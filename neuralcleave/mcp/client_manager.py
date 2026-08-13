"""Tracks named connections to external MCP servers and their registered tools.

Mirrors the single-process-tracking pattern of ``mcp.spawn.MCP_PROCESS`` (and
``tools.approvals.APPROVAL_QUEUE``) but for outbound client connections, of
which there can be several at once — one per external MCP server the
operator has configured (e.g. a company's internal-tools server, another
agent's server).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from neuralcleave.mcp.client import McpClient
from neuralcleave.mcp.client_tool import McpClientTool
from neuralcleave.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class _Connection:
    client: McpClient
    tool_names: list[str] = field(default_factory=list)


class McpClientManager:
    """Connects to, tracks, and disconnects from external MCP servers."""

    def __init__(self) -> None:
        self._connections: dict[str, _Connection] = {}

    @property
    def names(self) -> list[str]:
        return sorted(self._connections)

    async def connect(self, name: str, command: list[str], tool_registry: ToolRegistry) -> list[str]:
        """Connect to an external MCP server and register its tools.

        Returns the list of local (namespaced) tool names that were
        registered.

        Raises:
            ValueError: *name* is already connected — call :meth:`disconnect`
                first to replace it.
        """
        if name in self._connections:
            raise ValueError(f"MCP client {name!r} is already connected")

        client = McpClient(command)
        await client.connect()
        try:
            descriptors = await client.list_tools()
        except Exception:
            await client.close()
            raise

        tool_names: list[str] = []
        for descriptor in descriptors:
            tool = McpClientTool(client, descriptor, server_name=name)
            tool_registry.register(tool)
            tool_names.append(tool.name)

        self._connections[name] = _Connection(client=client, tool_names=tool_names)
        logger.info("mcp.client connected name=%s tools=%s", name, tool_names)
        return tool_names

    async def disconnect(self, name: str, tool_registry: ToolRegistry) -> bool:
        """Disconnect *name* and unregister its tools.

        Returns False if *name* was not connected.
        """
        conn = self._connections.pop(name, None)
        if conn is None:
            return False

        for tool_name in conn.tool_names:
            tool_registry.unregister(tool_name)
        await conn.client.close()
        logger.info("mcp.client disconnected name=%s", name)
        return True

    def list_clients(self) -> dict[str, list[str]]:
        """Return ``{server_name: [registered tool names]}`` for every connected server."""
        return {name: list(conn.tool_names) for name, conn in self._connections.items()}


# Module-level singleton — mirrors MCP_PROCESS / APPROVAL_QUEUE / AUDIT_LOG.
MCP_CLIENTS = McpClientManager()
