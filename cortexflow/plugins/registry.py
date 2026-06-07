"""Plugin registry — discover, load, and manage installed plugins.

Plugins are discovered via Python entry points (PEP 451):

    [project.entry-points."cortexflow.plugins"]
    my-plugin = "my_package.plugin:MyPlugin"

When ``PluginRegistry.discover()`` is called, it iterates all installed
packages that declare this entry point and instantiates the plugin class.

Plugins can also be registered manually for testing:

    registry = PluginRegistry(tool_registry)
    registry.register(MyPlugin())
    await registry.load_all()

Usage in gateway startup::

    tool_registry = ToolRegistry.default()
    plugin_registry = PluginRegistry(tool_registry)
    await plugin_registry.discover()
    await plugin_registry.load_all()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cortexflow.plugins.base import Plugin

if TYPE_CHECKING:
    from cortexflow.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "cortexflow.plugins"


class PluginRegistry:
    """Discovers, loads, and tracks installed CortexFlow plugins.

    Args:
        tool_registry: The ToolRegistry to populate with plugin-provided tools.
    """

    def __init__(self, tool_registry: "ToolRegistry | None" = None) -> None:
        self._tool_registry = tool_registry
        self._plugins: dict[str, Plugin] = {}
        self._loaded: set[str] = set()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[str]:
        """Scan installed packages for cortexflow.plugins entry points.

        Returns list of discovered plugin names (not yet loaded).
        """
        discovered: list[str] = []
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group=_ENTRY_POINT_GROUP)
            for ep in eps:
                try:
                    plugin_cls = ep.load()
                    plugin = plugin_cls()
                    self._plugins[plugin.metadata.name] = plugin
                    discovered.append(plugin.metadata.name)
                    logger.info("plugin.discovered name=%s type=%s", plugin.metadata.name, plugin.metadata.plugin_type)
                except Exception as exc:
                    logger.warning("plugin.discover failed ep=%s: %s", ep.name, exc)
        except Exception as exc:
            logger.warning("plugin.discover entry_points error: %s", exc)

        return discovered

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, plugin: Plugin) -> None:
        """Manually register a plugin instance (e.g. for testing)."""
        self._plugins[plugin.metadata.name] = plugin
        logger.debug("plugin.registered name=%s", plugin.metadata.name)

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)
        self._loaded.discard(name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def load_all(self) -> int:
        """Call on_load() for all registered plugins and wire their contributions.

        Returns count of successfully loaded plugins.
        """
        loaded = 0
        for name, plugin in list(self._plugins.items()):
            if name in self._loaded:
                continue
            try:
                await plugin.on_load()
                self._wire(plugin)
                self._loaded.add(name)
                loaded += 1
                logger.info("plugin.loaded name=%s", name)
            except Exception as exc:
                logger.error("plugin.load failed name=%s: %s", name, exc)

        return loaded

    async def unload_all(self) -> None:
        """Gracefully unload all loaded plugins."""
        for name in list(self._loaded):
            plugin = self._plugins.get(name)
            if plugin:
                try:
                    await plugin.on_unload()
                except Exception as exc:
                    logger.warning("plugin.unload error name=%s: %s", name, exc)
        self._loaded.clear()

    # ------------------------------------------------------------------

    def _wire(self, plugin: Plugin) -> None:
        """Wire plugin contributions into the tool registry."""
        if self._tool_registry is not None:
            for tool in plugin.get_tools():
                self._tool_registry.register(tool)
                logger.debug("plugin.wired tool=%s from plugin=%s", tool.name, plugin.metadata.name)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def all_plugins(self) -> list[Plugin]:
        return list(self._plugins.values())

    @property
    def loaded_count(self) -> int:
        return len(self._loaded)

    def is_loaded(self, name: str) -> bool:
        return name in self._loaded
