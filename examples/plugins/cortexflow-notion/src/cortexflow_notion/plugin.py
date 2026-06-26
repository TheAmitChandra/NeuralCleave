"""NotionPlugin — registers NotionSearchTool with the CortexFlow gateway."""

from __future__ import annotations

import os

from cortexflow_sdk import Plugin, PluginMetadata

from cortexflow_notion.tool import NotionSearchTool


class NotionPlugin(Plugin):
    """Adds a notion_search tool. Reads NOTION_TOKEN from the environment."""

    metadata = PluginMetadata(
        name="cortexflow-notion",
        version="0.1.0",
        plugin_type="tool",
        description="Search Notion pages and databases.",
        permissions=["network"],
        homepage="https://github.com/TheAmitChandra/CortexFlow",
    )

    def __init__(self) -> None:
        self._token = os.getenv("NOTION_TOKEN")

    def get_tools(self):
        return [NotionSearchTool(token=self._token)]
