"""Unit tests for cortexflow_sdk.plugins — Plugin / PluginMetadata."""

from __future__ import annotations

import pytest
from cortexflow_sdk import ChannelAdapter, Plugin, PluginMetadata, Tool, ToolResult


def test_plugin_metadata_defaults():
    meta = PluginMetadata(name="x", version="1.0", plugin_type="generic", description="d")
    assert meta.permissions == []
    assert meta.author == ""
    assert meta.homepage == ""


class _NoopPlugin(Plugin):
    metadata = PluginMetadata(
        name="noop", version="0.1", plugin_type="generic", description="Does nothing.",
    )


@pytest.mark.asyncio
async def test_default_lifecycle_hooks_are_noops():
    p = _NoopPlugin()
    await p.on_load()
    await p.on_unload()  # neither should raise


def test_default_get_tools_returns_empty_list():
    assert _NoopPlugin().get_tools() == []


def test_default_get_channel_adapter_returns_none():
    assert _NoopPlugin().get_channel_adapter() is None


def test_default_get_config_schema():
    assert _NoopPlugin().get_config_schema() == {"type": "object", "properties": {}}


def test_plugin_repr():
    assert repr(_NoopPlugin()) == "Plugin('noop' v0.1, type='generic')"


class _GreetTool(Tool):
    name = "greet"
    description = "Greets someone."
    parameters = {"name": {"type": "str", "description": "Name", "required": True}}

    async def execute(self, name: str) -> ToolResult:
        return ToolResult(tool=self.name, output=f"Hello, {name}!")


class _ToolPlugin(Plugin):
    metadata = PluginMetadata(
        name="greeter", version="1.0", plugin_type="tool", description="Adds a greet tool.",
    )

    def get_tools(self):
        return [_GreetTool()]


def test_tool_plugin_contributes_tool():
    tools = _ToolPlugin().get_tools()
    assert len(tools) == 1
    assert tools[0].name == "greet"


class _StubChannelAdapter(ChannelAdapter):
    channel_id = "stub"

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def send(self, target, text, *, reply_to=None, attachments=None):
        return None


class _ChannelPlugin(Plugin):
    metadata = PluginMetadata(
        name="stub-channel", version="1.0", plugin_type="channel", description="Adds a stub channel.",
    )

    def get_channel_adapter(self):
        return _StubChannelAdapter({})


def test_channel_plugin_contributes_adapter():
    adapter = _ChannelPlugin().get_channel_adapter()
    assert adapter is not None
    assert adapter.channel_id == "stub"
