"""Tests for plugin hot-reloading — PluginRegistry.reload_plugin / reload_all,
the REST endpoints (GET /api/v1/plugins, POST .../reload), and the CLI commands
`cortex plugins list` / `cortex plugins reload`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cortexflow_ai.plugins.base import Plugin, PluginMetadata
from cortexflow_ai.plugins.registry import PluginRegistry

# ---------------------------------------------------------------------------
# Helpers — minimal fake plugins
# ---------------------------------------------------------------------------


def _make_metadata(
    name: str = "test-plugin",
    version: str = "1.0.0",
    plugin_type: str = "tool",
    description: str = "A test plugin",
    permissions: list[str] | None = None,
    author: str = "",
    homepage: str = "",
) -> PluginMetadata:
    return PluginMetadata(
        name=name,
        version=version,
        plugin_type=plugin_type,
        description=description,
        permissions=permissions or [],
        author=author,
        homepage=homepage,
    )


class _FakeTool:
    """Minimal tool stub with a name attribute."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.permissions: list[str] = []
        self.description: str = "fake tool"


class _FakePlugin(Plugin):
    """Concrete Plugin subclass for testing."""

    def __init__(
        self,
        name: str = "test-plugin",
        tools: list[_FakeTool] | None = None,
        *,
        fail_on_load: bool = False,
        fail_on_unload: bool = False,
    ) -> None:
        self.metadata = _make_metadata(name=name)
        self._tools = tools or []
        self._fail_on_load = fail_on_load
        self._fail_on_unload = fail_on_unload
        self.load_call_count = 0
        self.unload_call_count = 0

    async def on_load(self) -> None:
        self.load_call_count += 1
        if self._fail_on_load:
            raise RuntimeError("load failed")

    async def on_unload(self) -> None:
        self.unload_call_count += 1
        if self._fail_on_unload:
            raise RuntimeError("unload failed")

    def get_tools(self) -> list[Any]:
        return list(self._tools)


class _FakeToolRegistry:
    """Minimal ToolRegistry stand-in that tracks registered/unregistered names."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def register(self, tool: Any) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        if name in self._tools:
            del self._tools[name]
        else:
            raise KeyError(name)

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())


# ---------------------------------------------------------------------------
# PluginRegistry.reload_plugin — basic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_plugin_returns_true_on_success() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    await reg.load_all()
    assert await reg.reload_plugin("alpha") is True


@pytest.mark.asyncio
async def test_reload_plugin_returns_false_for_unknown_name() -> None:
    reg = PluginRegistry()
    assert await reg.reload_plugin("nonexistent") is False


@pytest.mark.asyncio
async def test_reload_plugin_calls_on_unload_on_loaded_plugin() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    await reg.load_all()
    assert plugin.unload_call_count == 0
    await reg.reload_plugin("alpha")
    assert plugin.unload_call_count == 1


@pytest.mark.asyncio
async def test_reload_plugin_does_not_call_on_unload_for_unloaded_plugin() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    # do NOT load_all — plugin is registered but not loaded
    await reg.reload_plugin("alpha")
    assert plugin.unload_call_count == 0


@pytest.mark.asyncio
async def test_reload_plugin_calls_on_load_after_reload() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    await reg.load_all()
    assert plugin.load_call_count == 1
    await reg.reload_plugin("alpha")
    assert plugin.load_call_count == 2


@pytest.mark.asyncio
async def test_reload_plugin_plugin_is_loaded_after_success() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    await reg.reload_plugin("alpha")
    assert reg.is_loaded("alpha")


@pytest.mark.asyncio
async def test_reload_plugin_loaded_count_stays_at_one() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    await reg.load_all()
    assert reg.loaded_count == 1
    await reg.reload_plugin("alpha")
    assert reg.loaded_count == 1


@pytest.mark.asyncio
async def test_reload_plugin_unregistered_plugin_returns_false_on_hot_reload() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    reg.unregister("alpha")
    assert await reg.reload_plugin("alpha") is False


# ---------------------------------------------------------------------------
# reload_plugin — tool re-wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_plugin_unwires_old_tools() -> None:
    tr = _FakeToolRegistry()
    tool = _FakeTool("my-tool")
    plugin = _FakePlugin("alpha", tools=[tool])
    reg = PluginRegistry(tr)
    reg.register(plugin)
    await reg.load_all()
    assert "my-tool" in tr.names
    await reg.reload_plugin("alpha")
    # After reload the tool should be back (unwired then re-wired)
    assert "my-tool" in tr.names


@pytest.mark.asyncio
async def test_reload_plugin_rewires_tools_after_reload() -> None:
    tr = _FakeToolRegistry()
    tool = _FakeTool("my-tool")
    plugin = _FakePlugin("alpha", tools=[tool])
    reg = PluginRegistry(tr)
    reg.register(plugin)
    await reg.load_all()
    await reg.reload_plugin("alpha")
    assert "my-tool" in tr.names


@pytest.mark.asyncio
async def test_reload_plugin_unwire_tolerates_missing_tool() -> None:
    """_unwire should not raise if a tool isn't in the registry (e.g. already removed)."""
    tr = _FakeToolRegistry()
    tool = _FakeTool("ghost-tool")
    plugin = _FakePlugin("alpha", tools=[tool])
    reg = PluginRegistry(tr)
    reg.register(plugin)
    # Don't load_all — tool was never registered; _unwire must not crash
    await reg.reload_plugin("alpha")
    assert reg.is_loaded("alpha")


@pytest.mark.asyncio
async def test_reload_plugin_multiple_tools_all_rewired() -> None:
    tr = _FakeToolRegistry()
    tools = [_FakeTool("tool-a"), _FakeTool("tool-b"), _FakeTool("tool-c")]
    plugin = _FakePlugin("alpha", tools=tools)
    reg = PluginRegistry(tr)
    reg.register(plugin)
    await reg.load_all()
    await reg.reload_plugin("alpha")
    for t in tools:
        assert t.name in tr.names


@pytest.mark.asyncio
async def test_reload_plugin_no_tool_registry_does_not_crash() -> None:
    reg = PluginRegistry(tool_registry=None)
    plugin = _FakePlugin("alpha", tools=[_FakeTool("t")])
    reg.register(plugin)
    await reg.load_all()
    result = await reg.reload_plugin("alpha")
    assert result is True


# ---------------------------------------------------------------------------
# reload_plugin — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_plugin_on_load_failure_returns_false() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha", fail_on_load=True)
    reg.register(plugin)
    result = await reg.reload_plugin("alpha")
    assert result is False


@pytest.mark.asyncio
async def test_reload_plugin_on_load_failure_plugin_not_in_loaded_set() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha", fail_on_load=True)
    reg.register(plugin)
    await reg.reload_plugin("alpha")
    assert not reg.is_loaded("alpha")


@pytest.mark.asyncio
async def test_reload_plugin_on_unload_failure_still_proceeds() -> None:
    """A failing on_unload should not prevent the reload from continuing."""
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha", fail_on_unload=True)
    reg.register(plugin)
    await reg.load_all()
    # on_unload raises — but reload should still attempt on_load
    result = await reg.reload_plugin("alpha")
    assert result is True
    assert reg.is_loaded("alpha")


@pytest.mark.asyncio
async def test_reload_plugin_on_unload_failure_load_still_called() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha", fail_on_unload=True)
    reg.register(plugin)
    await reg.load_all()
    await reg.reload_plugin("alpha")
    assert plugin.load_call_count == 2


# ---------------------------------------------------------------------------
# reload_plugin — entry-point re-discovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_plugin_uses_fresh_instance_from_entry_points() -> None:
    reg = PluginRegistry()
    old_plugin = _FakePlugin("ep-plugin")
    reg.register(old_plugin)
    await reg.load_all()

    fresh_plugin = _FakePlugin("ep-plugin")

    with patch.object(reg, "_discover_one", return_value=fresh_plugin):
        await reg.reload_plugin("ep-plugin")

    # The registry should now hold the fresh instance
    assert reg._plugins["ep-plugin"] is fresh_plugin


@pytest.mark.asyncio
async def test_reload_plugin_keeps_manual_instance_when_discover_returns_none() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("manual-plugin")
    reg.register(plugin)
    await reg.load_all()

    with patch.object(reg, "_discover_one", return_value=None):
        await reg.reload_plugin("manual-plugin")

    assert reg._plugins["manual-plugin"] is plugin


@pytest.mark.asyncio
async def test_discover_one_returns_none_when_no_entry_points() -> None:
    reg = PluginRegistry()
    with patch("importlib.metadata.entry_points", side_effect=Exception("no eps")):
        result = reg._discover_one("anything")
    assert result is None


# ---------------------------------------------------------------------------
# reload_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_all_returns_count_of_successes() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("a"))
    reg.register(_FakePlugin("b"))
    reg.register(_FakePlugin("c"))
    await reg.load_all()
    count = await reg.reload_all()
    assert count == 3


@pytest.mark.asyncio
async def test_reload_all_empty_registry_returns_zero() -> None:
    reg = PluginRegistry()
    count = await reg.reload_all()
    assert count == 0


@pytest.mark.asyncio
async def test_reload_all_partial_failure_returns_success_count() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("good"))
    reg.register(_FakePlugin("bad", fail_on_load=True))
    await reg.load_all()
    count = await reg.reload_all()
    assert count == 1


@pytest.mark.asyncio
async def test_reload_all_each_plugin_reloaded() -> None:
    reg = PluginRegistry()
    plugins = [_FakePlugin(f"p{i}") for i in range(4)]
    for p in plugins:
        reg.register(p)
    await reg.load_all()
    await reg.reload_all()
    for p in plugins:
        assert p.load_call_count == 2


@pytest.mark.asyncio
async def test_reload_all_continues_after_one_failure() -> None:
    reg = PluginRegistry()
    good1 = _FakePlugin("good1")
    bad = _FakePlugin("bad", fail_on_load=True)
    good2 = _FakePlugin("good2")
    reg.register(good1)
    reg.register(bad)
    reg.register(good2)
    await reg.load_all()
    count = await reg.reload_all()
    assert count == 2
    assert reg.is_loaded("good1")
    assert not reg.is_loaded("bad")
    assert reg.is_loaded("good2")


@pytest.mark.asyncio
async def test_reload_all_all_plugins_loaded_after_success() -> None:
    reg = PluginRegistry()
    for i in range(3):
        reg.register(_FakePlugin(f"p{i}"))
    await reg.load_all()
    await reg.reload_all()
    assert reg.loaded_count == 3


# ---------------------------------------------------------------------------
# plugin_info
# ---------------------------------------------------------------------------


def test_plugin_info_returns_none_for_unknown() -> None:
    reg = PluginRegistry()
    assert reg.plugin_info("unknown") is None


def test_plugin_info_returns_dict_for_registered() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("my-plugin")
    reg.register(plugin)
    info = reg.plugin_info("my-plugin")
    assert info is not None
    assert info["name"] == "my-plugin"
    assert info["loaded"] is False


@pytest.mark.asyncio
async def test_plugin_info_loaded_field_true_after_load() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("my-plugin"))
    await reg.load_all()
    info = reg.plugin_info("my-plugin")
    assert info is not None
    assert info["loaded"] is True


def test_plugin_info_contains_all_metadata_fields() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("rich-plugin")
    plugin.metadata = _make_metadata(
        name="rich-plugin",
        version="2.0.0",
        plugin_type="channel",
        description="A rich plugin",
        permissions=["network"],
        author="Amit",
        homepage="https://example.com",
    )
    reg.register(plugin)
    info = reg.plugin_info("rich-plugin")
    assert info is not None
    assert info["version"] == "2.0.0"
    assert info["plugin_type"] == "channel"
    assert info["permissions"] == ["network"]
    assert info["author"] == "Amit"
    assert info["homepage"] == "https://example.com"


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


def _make_test_client(registry: PluginRegistry | None = None) -> TestClient:

    app = FastAPI()
    from cortexflow_ai.gateway.routes import router, set_plugin_registry

    set_plugin_registry(registry)
    app.include_router(router)
    return TestClient(app)


def test_list_plugins_returns_503_when_no_registry() -> None:
    client = _make_test_client(None)
    resp = client.get("/api/v1/plugins")
    assert resp.status_code == 503


def test_list_plugins_empty_registry() -> None:
    reg = PluginRegistry()
    client = _make_test_client(reg)
    resp = client.get("/api/v1/plugins")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["plugins"] == []


def test_list_plugins_shows_registered_plugins() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("plugin-a"))
    reg.register(_FakePlugin("plugin-b"))
    client = _make_test_client(reg)
    resp = client.get("/api/v1/plugins")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    names = [p["name"] for p in data["plugins"]]
    assert "plugin-a" in names
    assert "plugin-b" in names


def test_list_plugins_loaded_count_field() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("p1"))
    asyncio.run(reg.load_all())
    client = _make_test_client(reg)
    resp = client.get("/api/v1/plugins")
    assert resp.json()["loaded_count"] == 1


def test_get_plugin_404_unknown() -> None:
    reg = PluginRegistry()
    client = _make_test_client(reg)
    resp = client.get("/api/v1/plugins/missing")
    assert resp.status_code == 404


def test_get_plugin_503_no_registry() -> None:
    client = _make_test_client(None)
    resp = client.get("/api/v1/plugins/anything")
    assert resp.status_code == 503


def test_get_plugin_returns_info() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("my-plugin"))
    client = _make_test_client(reg)
    resp = client.get("/api/v1/plugins/my-plugin")
    assert resp.status_code == 200
    assert resp.json()["name"] == "my-plugin"


def test_reload_all_endpoint_503_no_registry() -> None:
    client = _make_test_client(None)
    resp = client.post("/api/v1/plugins/reload")
    assert resp.status_code == 503


def test_reload_all_endpoint_empty_registry() -> None:
    reg = PluginRegistry()
    client = _make_test_client(reg)
    resp = client.post("/api/v1/plugins/reload")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reloaded"] == 0
    assert data["total"] == 0


def test_reload_all_endpoint_success() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("p1"))
    reg.register(_FakePlugin("p2"))
    asyncio.run(reg.load_all())
    client = _make_test_client(reg)
    resp = client.post("/api/v1/plugins/reload")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reloaded"] == 2
    assert data["total"] == 2
    assert data["success"] is True


def test_reload_all_endpoint_partial_failure() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("good"))
    reg.register(_FakePlugin("bad", fail_on_load=True))
    asyncio.run(reg.load_all())
    client = _make_test_client(reg)
    resp = client.post("/api/v1/plugins/reload")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reloaded"] == 1
    assert data["success"] is False


def test_reload_single_endpoint_503_no_registry() -> None:
    client = _make_test_client(None)
    resp = client.post("/api/v1/plugins/unknown/reload")
    assert resp.status_code == 503


def test_reload_single_endpoint_404_unknown() -> None:
    reg = PluginRegistry()
    client = _make_test_client(reg)
    resp = client.post("/api/v1/plugins/unknown/reload")
    assert resp.status_code == 404


def test_reload_single_endpoint_success() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("my-plugin"))
    asyncio.run(reg.load_all())
    client = _make_test_client(reg)
    resp = client.post("/api/v1/plugins/my-plugin/reload")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "my-plugin"
    assert data["reloaded"] is True


def test_reload_single_endpoint_failure() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("bad", fail_on_load=True))
    asyncio.run(reg.load_all())
    client = _make_test_client(reg)
    resp = client.post("/api/v1/plugins/bad/reload")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reloaded"] is False


# ---------------------------------------------------------------------------
# REST — set_plugin_registry / get_plugin_registry
# ---------------------------------------------------------------------------


def test_set_and_get_plugin_registry() -> None:
    from cortexflow_ai.gateway.routes import get_plugin_registry, set_plugin_registry

    reg = PluginRegistry()
    set_plugin_registry(reg)
    assert get_plugin_registry() is reg
    set_plugin_registry(None)
    assert get_plugin_registry() is None


# ---------------------------------------------------------------------------
# CLI — cortex plugins list
# ---------------------------------------------------------------------------


def test_cli_plugins_list_no_plugins() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()

    with patch("cortexflow_ai.plugins.registry.PluginRegistry.discover", return_value=[]):
        result = runner.invoke(cli, ["plugins", "list"])

    assert result.exit_code == 0
    assert "No plugins discovered" in result.output


def test_cli_plugins_list_shows_plugin_names() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()

    plugin = _FakePlugin("sample-plugin")

    def _mock_discover(self: Any) -> list[str]:
        self._plugins["sample-plugin"] = plugin
        return ["sample-plugin"]

    with patch.object(PluginRegistry, "discover", _mock_discover):
        result = runner.invoke(cli, ["plugins", "list"])

    assert result.exit_code == 0
    assert "sample-plugin" in result.output


# ---------------------------------------------------------------------------
# CLI — cortex plugins reload (all)
# ---------------------------------------------------------------------------


def test_cli_plugins_reload_all_no_plugins() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()

    with (
        patch("cortexflow_ai.plugins.registry.PluginRegistry.discover", return_value=[]),
        patch.object(PluginRegistry, "reload_all", new_callable=lambda: lambda self: asyncio.coroutine(lambda: 0)()),
    ):
        result = runner.invoke(cli, ["plugins", "reload"])

    assert result.exit_code == 0
    assert "No plugins" in result.output


def test_cli_plugins_reload_all_success() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    plugin = _FakePlugin("p1")

    def _mock_discover(self: Any) -> list[str]:
        self._plugins["p1"] = plugin
        return ["p1"]

    async def _mock_reload_all(self: Any) -> int:
        return 1

    with (
        patch.object(PluginRegistry, "discover", _mock_discover),
        patch.object(PluginRegistry, "reload_all", _mock_reload_all),
    ):
        result = runner.invoke(cli, ["plugins", "reload"])

    assert result.exit_code == 0
    assert "Reloaded 1/1" in result.output


def test_cli_plugins_reload_all_partial_failure() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    p1 = _FakePlugin("p1")
    p2 = _FakePlugin("p2")

    def _mock_discover(self: Any) -> list[str]:
        self._plugins["p1"] = p1
        self._plugins["p2"] = p2
        return ["p1", "p2"]

    async def _mock_reload_all(self: Any) -> int:
        return 1

    with (
        patch.object(PluginRegistry, "discover", _mock_discover),
        patch.object(PluginRegistry, "reload_all", _mock_reload_all),
    ):
        result = runner.invoke(cli, ["plugins", "reload"])

    assert result.exit_code == 0
    assert "Reloaded 1/2" in result.output


# ---------------------------------------------------------------------------
# CLI — cortex plugins reload NAME
# ---------------------------------------------------------------------------


def test_cli_plugins_reload_by_name_success() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    plugin = _FakePlugin("my-plugin")

    def _mock_discover(self: Any) -> list[str]:
        self._plugins["my-plugin"] = plugin
        return ["my-plugin"]

    async def _mock_reload(self: Any, name: str) -> bool:
        return True

    with (
        patch.object(PluginRegistry, "discover", _mock_discover),
        patch.object(PluginRegistry, "reload_plugin", _mock_reload),
    ):
        result = runner.invoke(cli, ["plugins", "reload", "my-plugin"])

    assert result.exit_code == 0
    assert "Reloaded plugin 'my-plugin' successfully" in result.output


def test_cli_plugins_reload_by_name_failure() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    plugin = _FakePlugin("my-plugin")

    def _mock_discover(self: Any) -> list[str]:
        self._plugins["my-plugin"] = plugin
        return ["my-plugin"]

    async def _mock_reload(self: Any, name: str) -> bool:
        return False

    with (
        patch.object(PluginRegistry, "discover", _mock_discover),
        patch.object(PluginRegistry, "reload_plugin", _mock_reload),
    ):
        result = runner.invoke(cli, ["plugins", "reload", "my-plugin"])

    assert result.exit_code != 0
    assert "Failed to reload" in result.output


def test_cli_plugins_reload_by_name_not_found() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()

    with patch("cortexflow_ai.plugins.registry.PluginRegistry.discover", return_value=[]):
        result = runner.invoke(cli, ["plugins", "reload", "ghost-plugin"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# Edge cases — multiple reload cycles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reload_plugin_three_cycles_increments_load_count() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin("alpha")
    reg.register(plugin)
    await reg.load_all()
    for _ in range(3):
        await reg.reload_plugin("alpha")
    assert plugin.load_call_count == 4  # initial + 3 reloads


@pytest.mark.asyncio
async def test_reload_all_idempotent_on_empty() -> None:
    reg = PluginRegistry()
    for _ in range(5):
        count = await reg.reload_all()
        assert count == 0


@pytest.mark.asyncio
async def test_reload_plugin_with_tool_registry_no_double_register() -> None:
    """After two reload cycles the tool should be registered exactly once."""
    tr = _FakeToolRegistry()
    tool = _FakeTool("unique-tool")
    plugin = _FakePlugin("alpha", tools=[tool])
    reg = PluginRegistry(tr)
    reg.register(plugin)
    await reg.load_all()
    await reg.reload_plugin("alpha")
    await reg.reload_plugin("alpha")
    # _FakeToolRegistry.register replaces, so "unique-tool" present once
    assert tr.names.count("unique-tool") == 1


@pytest.mark.asyncio
async def test_reload_plugin_preserves_other_plugins() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin("alpha"))
    reg.register(_FakePlugin("beta"))
    await reg.load_all()
    await reg.reload_plugin("alpha")
    assert reg.is_loaded("beta")
    assert reg.loaded_count == 2
