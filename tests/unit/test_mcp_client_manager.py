"""Tests for McpClientManager — connect/disconnect lifecycle for external MCP servers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.mcp.client_manager import McpClientManager
from neuralcleave.mcp.protocol import McpToolDescriptor
from neuralcleave.tools.registry import ToolRegistry


def _patch_client(list_tools_result=None, connect_result=None):
    """Patch McpClient so connect() doesn't spawn a real subprocess."""
    instance = AsyncMock()
    instance.connect = AsyncMock(return_value=connect_result or {})
    instance.list_tools = AsyncMock(return_value=list_tools_result or [])
    instance.close = AsyncMock()
    return patch("neuralcleave.mcp.client_manager.McpClient", return_value=instance), instance


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_registers_discovered_tools(self) -> None:
        descriptors = [McpToolDescriptor(name="search", description="Search.", input_schema={})]
        patcher, _instance = _patch_client(list_tools_result=descriptors)
        registry = ToolRegistry()
        manager = McpClientManager()

        with patcher:
            tool_names = await manager.connect("acme", ["fake"], registry)

        assert tool_names == ["mcp_acme_search"]
        assert registry.get("mcp_acme_search") is not None

    @pytest.mark.asyncio
    async def test_connect_records_name_in_names_property(self) -> None:
        patcher, _instance = _patch_client()
        manager = McpClientManager()

        with patcher:
            await manager.connect("acme", ["fake"], ToolRegistry())

        assert manager.names == ["acme"]

    @pytest.mark.asyncio
    async def test_connect_duplicate_name_raises_value_error(self) -> None:
        patcher, _instance = _patch_client()
        manager = McpClientManager()

        with patcher:
            await manager.connect("acme", ["fake"], ToolRegistry())
            with pytest.raises(ValueError, match="already connected"):
                await manager.connect("acme", ["fake"], ToolRegistry())

    @pytest.mark.asyncio
    async def test_connect_closes_client_if_list_tools_fails(self) -> None:
        instance = AsyncMock()
        instance.connect = AsyncMock(return_value={})
        instance.list_tools = AsyncMock(side_effect=RuntimeError("boom"))
        instance.close = AsyncMock()
        manager = McpClientManager()

        with patch("neuralcleave.mcp.client_manager.McpClient", return_value=instance):
            with pytest.raises(RuntimeError, match="boom"):
                await manager.connect("acme", ["fake"], ToolRegistry())

        instance.close.assert_awaited_once()
        assert manager.names == []


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_unregisters_tools(self) -> None:
        descriptors = [McpToolDescriptor(name="search", description="Search.", input_schema={})]
        patcher, instance = _patch_client(list_tools_result=descriptors)
        registry = ToolRegistry()
        manager = McpClientManager()

        with patcher:
            await manager.connect("acme", ["fake"], registry)
            ok = await manager.disconnect("acme", registry)

        assert ok is True
        assert registry.get("mcp_acme_search") is None
        instance.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_unknown_name_returns_false(self) -> None:
        manager = McpClientManager()
        ok = await manager.disconnect("nope", ToolRegistry())
        assert ok is False

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_names(self) -> None:
        patcher, _instance = _patch_client()
        manager = McpClientManager()

        with patcher:
            await manager.connect("acme", ["fake"], ToolRegistry())
            await manager.disconnect("acme", ToolRegistry())

        assert manager.names == []


class TestListClients:
    @pytest.mark.asyncio
    async def test_list_clients_maps_name_to_tool_names(self) -> None:
        descriptors = [
            McpToolDescriptor(name="search", description="", input_schema={}),
            McpToolDescriptor(name="fetch", description="", input_schema={}),
        ]
        patcher, _instance = _patch_client(list_tools_result=descriptors)
        manager = McpClientManager()

        with patcher:
            await manager.connect("acme", ["fake"], ToolRegistry())

        clients = manager.list_clients()
        assert clients == {"acme": ["mcp_acme_search", "mcp_acme_fetch"]}

    def test_list_clients_empty_when_none_connected(self) -> None:
        manager = McpClientManager()
        assert manager.list_clients() == {}
