"""NotionPlugin — registers NotionSearchTool with the NeuralCleave gateway."""

from __future__ import annotations

import os

from neuralcleave_sdk import Plugin, PluginMetadata

from neuralcleave_notion.tool import NotionSearchTool


class NotionPlugin(Plugin):
    """Adds a notion_search tool. Reads NOTION_TOKEN from the environment."""

    metadata = PluginMetadata(
        name="neuralcleave-notion",
        version="0.1.0",
        plugin_type="tool",
        description="Search Notion pages and databases.",
        permissions=["network"],
        homepage="https://github.com/TheAmitChandra/NeuralCleave",
    )

    def __init__(self) -> None:
        self._token = os.getenv("NOTION_TOKEN")

    def get_tools(self):
        return [NotionSearchTool(token=self._token)]
