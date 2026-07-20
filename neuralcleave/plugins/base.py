"""Plugin base class — the contract every NeuralCleave plugin must satisfy.

A plugin is a Python package installed via ``pip install <name>`` that:
  - Declares a ``NeuralCleave_plugin`` entry point pointing to a Plugin subclass
  - Provides one or more tools, channel adapters, or TTS/STT backends
  - Declares its capabilities and required permissions upfront

Plugin types:
    "tool"      — adds Tool instances to the ToolRegistry
    "channel"   — adds a ChannelAdapter to the gateway
    "tts"       — alternative TTS backend
    "stt"       — alternative STT backend
    "memory"    — alternative memory tier
    "generic"   — anything else (lifecycle hooks, middleware)

Example plugin (in a separate package)::

    # NeuralCleave_github/plugin.py
    from neuralcleave.plugins.base import Plugin, PluginMetadata

    class GitHubPlugin(Plugin):
        metadata = PluginMetadata(
            name="NeuralCleave-github",
            version="1.0.0",
            plugin_type="tool",
            description="GitHub integration — PRs, issues, commits",
            permissions=["network"],
        )

        def get_tools(self):
            from .tools import GitHubTool
            return [GitHubTool()]

    # In pyproject.toml:
    # [project.entry-points."NeuralCleave.plugins"]
    # NeuralCleave-github = "NeuralCleave_github.plugin:GitHubPlugin"
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neuralcleave.channels.base import ChannelAdapter
    from neuralcleave.tools.base import Tool


@dataclass
class PluginMetadata:
    """Metadata that every plugin must declare."""

    name: str
    version: str
    plugin_type: str  # "tool" | "channel" | "tts" | "stt" | "memory" | "generic"
    description: str
    permissions: list[str] = field(default_factory=list)
    author: str = ""
    homepage: str = ""


class Plugin(ABC):
    """Abstract base for all NeuralCleave plugins.

    Subclass this and implement the methods that apply to your plugin_type.
    Unimplemented optional methods return empty lists/None by default.
    """

    metadata: PluginMetadata

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_load(self) -> None:
        """Called once when the plugin is loaded. Perform async init here."""

    async def on_unload(self) -> None:
        """Called when the plugin is unloaded (e.g. on gateway shutdown)."""

    # ------------------------------------------------------------------
    # Type-specific contribution methods
    # ------------------------------------------------------------------

    def get_tools(self) -> list["Tool"]:
        """Return Tool instances contributed by this plugin (type=tool)."""
        return []

    def get_channel_adapter(self) -> "ChannelAdapter | None":
        """Return a ChannelAdapter contributed by this plugin (type=channel)."""
        return None

    def get_config_schema(self) -> dict[str, Any]:
        """Return JSON Schema for plugin-specific config options."""
        return {"type": "object", "properties": {}}

    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Plugin({self.metadata.name!r} v{self.metadata.version}, type={self.metadata.plugin_type!r})"
