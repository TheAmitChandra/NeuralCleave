"""Tests for neuralcleave.mcp.server's _main() entrypoint.

Round 4 (2026-08-21 gap analysis) P0 follow-up: confirms the MCP entrypoint
deliberately never enables the exec-approval gate, since an MCP client has
no chat channel a pending approval could be forwarded into.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.mcp.server import McpServer, _main


@pytest.mark.asyncio
async def test_main_builds_a_registry_with_the_approval_gate_off() -> None:
    captured: dict[str, McpServer] = {}

    class _RecordingServer(McpServer):
        def __init__(self, registry) -> None:
            super().__init__(registry=registry)
            captured["server"] = self

    with patch("neuralcleave.mcp.server.McpServer", _RecordingServer):
        with patch.object(McpServer, "run", new=AsyncMock()):
            await _main()

    shell = captured["server"]._adapter._registry.get("shell")
    assert shell._require_approval is False
