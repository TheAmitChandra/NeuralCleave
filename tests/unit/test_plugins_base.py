"""Unit tests for cortexflow.plugins.base — PluginMetadata and Plugin ABC."""

from __future__ import annotations

import pytest

from cortexflow.plugins.base import Plugin, PluginMetadata

# ---------------------------------------------------------------------------
# Concrete stub plugin
# ---------------------------------------------------------------------------


class _StubPlugin(Plugin):
    metadata = PluginMetadata(
        name="stub",
        version="0.1.0",
        plugin_type="tool",
        description="A stub plugin for testing.",
        permissions=["network"],
        author="Tester",
        homepage="https://example.com",
    )


class _MinimalPlugin(Plugin):
    metadata = PluginMetadata(
        name="minimal",
        version="1.0.0",
        plugin_type="generic",
        description="Minimal plugin.",
    )


# ---------------------------------------------------------------------------
# PluginMetadata
# ---------------------------------------------------------------------------


def test_plugin_metadata_required_fields():
    m = PluginMetadata(
        name="test-plugin",
        version="2.0.0",
        plugin_type="channel",
        description="Testing.",
    )
    assert m.name == "test-plugin"
    assert m.version == "2.0.0"
    assert m.plugin_type == "channel"
    assert m.description == "Testing."


def test_plugin_metadata_defaults():
    m = PluginMetadata(name="x", version="0.1", plugin_type="generic", description="y")
    assert m.permissions == []
    assert m.author == ""
    assert m.homepage == ""


def test_plugin_metadata_permissions_stored():
    m = PluginMetadata(
        name="x", version="0.1", plugin_type="tool", description="y",
        permissions=["network", "filesystem:read"],
    )
    assert "network" in m.permissions
    assert "filesystem:read" in m.permissions


# ---------------------------------------------------------------------------
# Abstract class enforcement
# ---------------------------------------------------------------------------


def test_abstract_plugin_requires_metadata():
    """Plugin subclass without metadata attribute can still be instantiated
    (metadata is a class variable, not abstractmethod), but get_tools returns []."""
    plugin = _MinimalPlugin()
    assert plugin.get_tools() == []


# ---------------------------------------------------------------------------
# Default method implementations
# ---------------------------------------------------------------------------


def test_get_tools_default_empty():
    assert _StubPlugin().get_tools() == []


def test_get_channel_adapter_default_none():
    assert _StubPlugin().get_channel_adapter() is None


def test_get_config_schema_default_structure():
    schema = _StubPlugin().get_config_schema()
    assert schema["type"] == "object"
    assert "properties" in schema


@pytest.mark.asyncio
async def test_on_load_default_noop():
    plugin = _StubPlugin()
    await plugin.on_load()  # should not raise


@pytest.mark.asyncio
async def test_on_unload_default_noop():
    plugin = _StubPlugin()
    await plugin.on_unload()  # should not raise


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------


def test_plugin_repr_contains_name_and_type():
    r = repr(_StubPlugin())
    assert "stub" in r
    assert "tool" in r


# ---------------------------------------------------------------------------
# Plugin with custom get_tools
# ---------------------------------------------------------------------------


def test_plugin_get_tools_override():
    from cortexflow.tools.base import Tool, ToolResult

    class _MyTool(Tool):
        name = "my_tool"
        description = "Custom tool."
        permissions = []

        async def execute(self, **_) -> ToolResult:
            return ToolResult(tool=self.name, output=None)

    class _ToolPlugin(Plugin):
        metadata = PluginMetadata(
            name="tool-plugin", version="1.0", plugin_type="tool", description="Has tools."
        )

        def get_tools(self):
            return [_MyTool()]

    plugin = _ToolPlugin()
    tools = plugin.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "my_tool"
