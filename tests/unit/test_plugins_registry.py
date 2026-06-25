"""Unit tests for cortexflow.plugins.registry — PluginRegistry lifecycle and wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cortexflow.plugins.base import Plugin, PluginMetadata
from cortexflow.plugins.registry import PluginRegistry
from cortexflow.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Stub plugin helpers
# ---------------------------------------------------------------------------


def _make_plugin(name: str, plugin_type: str = "generic") -> Plugin:
    class _P(Plugin):
        metadata = PluginMetadata(
            name=name, version="0.1", plugin_type=plugin_type, description=f"Plugin {name}"
        )
        on_load_called = False
        on_unload_called = False

        async def on_load(self) -> None:
            _P.on_load_called = True

        async def on_unload(self) -> None:
            _P.on_unload_called = True

    return _P()


def _make_tool_plugin(name: str, tool_name: str) -> Plugin:
    from cortexflow.tools.base import Tool, ToolResult

    class _T(Tool):
        name = tool_name
        description = "A contributed tool."
        permissions = []

        async def execute(self, **_) -> ToolResult:
            return ToolResult(tool=self.name, output=None)

    class _P(Plugin):
        metadata = PluginMetadata(
            name=name, version="0.1", plugin_type="tool", description=f"Tool plugin {name}"
        )

        def get_tools(self):
            return [_T()]

    return _P()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_adds_plugin():
    registry = PluginRegistry()
    plugin = _make_plugin("test-plugin")
    registry.register(plugin)
    assert "test-plugin" in [p.metadata.name for p in registry.all_plugins]


def test_unregister_removes_plugin():
    registry = PluginRegistry()
    plugin = _make_plugin("to-remove")
    registry.register(plugin)
    registry.unregister("to-remove")
    assert "to-remove" not in [p.metadata.name for p in registry.all_plugins]


def test_all_plugins_empty_initially():
    registry = PluginRegistry()
    assert registry.all_plugins == []


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_all_calls_on_load():
    registry = PluginRegistry()
    loaded_names = []

    class _TrackPlugin(Plugin):
        metadata = PluginMetadata(name="tracker", version="0.1", plugin_type="generic", description="x")

        async def on_load(self) -> None:
            loaded_names.append("tracker")

    registry.register(_TrackPlugin())
    count = await registry.load_all()
    assert count == 1
    assert "tracker" in loaded_names


@pytest.mark.asyncio
async def test_load_all_returns_count():
    registry = PluginRegistry()
    registry.register(_make_plugin("a"))
    registry.register(_make_plugin("b"))
    count = await registry.load_all()
    assert count == 2


@pytest.mark.asyncio
async def test_load_all_does_not_load_twice():
    registry = PluginRegistry()
    registry.register(_make_plugin("once"))
    await registry.load_all()
    count = await registry.load_all()  # second call — nothing new to load
    assert count == 0


@pytest.mark.asyncio
async def test_loaded_count_tracks_loaded():
    registry = PluginRegistry()
    registry.register(_make_plugin("x"))
    assert registry.loaded_count == 0
    await registry.load_all()
    assert registry.loaded_count == 1


@pytest.mark.asyncio
async def test_is_loaded_returns_true_after_load():
    registry = PluginRegistry()
    registry.register(_make_plugin("check-me"))
    assert not registry.is_loaded("check-me")
    await registry.load_all()
    assert registry.is_loaded("check-me")


@pytest.mark.asyncio
async def test_unload_all_calls_on_unload():
    unloaded = []

    class _UPlugin(Plugin):
        metadata = PluginMetadata(name="u", version="0.1", plugin_type="generic", description="u")

        async def on_unload(self) -> None:
            unloaded.append("u")

    registry = PluginRegistry()
    registry.register(_UPlugin())
    await registry.load_all()
    await registry.unload_all()
    assert "u" in unloaded
    assert registry.loaded_count == 0


@pytest.mark.asyncio
async def test_load_error_continues_loading_others():
    class _BadPlugin(Plugin):
        metadata = PluginMetadata(name="bad", version="0.1", plugin_type="generic", description="bad")

        async def on_load(self) -> None:
            raise RuntimeError("load failure")

    registry = PluginRegistry()
    registry.register(_BadPlugin())
    registry.register(_make_plugin("good"))
    count = await registry.load_all()
    # "good" should still load
    assert count == 1
    assert registry.is_loaded("good")
    assert not registry.is_loaded("bad")


# ---------------------------------------------------------------------------
# Tool wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_wires_plugin_tools_into_tool_registry():
    tool_registry = ToolRegistry()
    plugin_registry = PluginRegistry(tool_registry=tool_registry)
    plugin_registry.register(_make_tool_plugin("wiring-plugin", "contributed_tool"))
    await plugin_registry.load_all()
    assert "contributed_tool" in tool_registry.names


@pytest.mark.asyncio
async def test_load_without_tool_registry_no_error():
    registry = PluginRegistry(tool_registry=None)
    registry.register(_make_tool_plugin("no-registry", "orphan_tool"))
    count = await registry.load_all()
    assert count == 1


# ---------------------------------------------------------------------------
# Discovery (entry points)
# ---------------------------------------------------------------------------


def test_discover_returns_empty_when_no_entry_points():
    registry = PluginRegistry()
    with patch("cortexflow.plugins.registry.entry_points", return_value=[], create=True):
        # Patch the importlib.metadata inside the module
        with patch("importlib.metadata.entry_points", return_value=[]):
            discovered = registry.discover()
    assert isinstance(discovered, list)


class _FakeEntryPoint:
    def __init__(self, name: str, loader):
        self.name = name
        self._loader = loader

    def load(self):
        return self._loader()


def _make_plugin_class(name: str):
    """Like _make_plugin, but returns the class (as ep.load() would)."""

    class _P(Plugin):
        metadata = PluginMetadata(
            name=name, version="0.1", plugin_type="generic", description=f"Plugin {name}"
        )

    return _P


def test_discover_loads_and_registers_plugin():
    registry = PluginRegistry()
    ep = _FakeEntryPoint("discovered-plugin", lambda: _make_plugin_class("discovered-plugin"))

    with patch("importlib.metadata.entry_points", return_value=[ep]):
        discovered = registry.discover()

    assert discovered == ["discovered-plugin"]
    assert "discovered-plugin" in [p.metadata.name for p in registry.all_plugins]


def test_discover_skips_entry_point_that_fails_to_load():
    registry = PluginRegistry()

    def _broken_loader():
        raise ImportError("broken plugin package")

    bad_ep = _FakeEntryPoint("broken", _broken_loader)
    good_ep = _FakeEntryPoint("ok", lambda: _make_plugin_class("ok-plugin"))

    with patch("importlib.metadata.entry_points", return_value=[bad_ep, good_ep]):
        discovered = registry.discover()

    assert discovered == ["ok-plugin"]


def test_discover_returns_empty_when_entry_points_call_raises():
    registry = PluginRegistry()
    with patch("importlib.metadata.entry_points", side_effect=RuntimeError("metadata broken")):
        discovered = registry.discover()
    assert discovered == []


# ---------------------------------------------------------------------------
# unload_all error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unload_all_continues_after_on_unload_error():
    class _BadUnloadPlugin(Plugin):
        metadata = PluginMetadata(name="bad-unload", version="0.1", plugin_type="generic", description="x")

        async def on_unload(self) -> None:
            raise RuntimeError("unload failure")

    registry = PluginRegistry()
    registry.register(_BadUnloadPlugin())
    await registry.load_all()

    await registry.unload_all()  # must not raise

    assert registry.loaded_count == 0
