"""GitHubPlugin — registers GitHubEventsTool with the NeuralCleave gateway."""

from __future__ import annotations

import os

from neuralcleave_sdk import Plugin, PluginMetadata

from neuralcleave_github.tool import GitHubEventsTool


class GitHubPlugin(Plugin):
    """Adds a github_events tool. Reads GITHUB_TOKEN from the environment."""

    metadata = PluginMetadata(
        name="neuralcleave-github",
        version="0.1.0",
        plugin_type="tool",
        description="List recent GitHub repository events (pushes, PRs, issues).",
        permissions=["network"],
        homepage="https://github.com/TheAmitChandra/NeuralCleave",
    )

    def __init__(self) -> None:
        self._token = os.getenv("GITHUB_TOKEN")

    def get_tools(self):
        return [GitHubEventsTool(token=self._token)]
