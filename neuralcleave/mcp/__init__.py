"""MCP (Model Context Protocol) server for NeuralCleave.

Exposes the registered tool set as MCP tools consumable by Claude Code,
Cursor, Codex, and other MCP-compatible clients via a stdio JSON-RPC 2.0
transport.

Usage (run as subprocess)::

    python -m neuralcleave.mcp.server

Or spawn from the gateway::

    POST /api/v1/mcp/spawn
"""

from neuralcleave.mcp.protocol import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpContent,
    McpToolDescriptor,
)
from neuralcleave.mcp.tool_adapter import McpToolAdapter

__all__ = [
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpContent",
    "McpToolAdapter",
    "McpToolDescriptor",
]
