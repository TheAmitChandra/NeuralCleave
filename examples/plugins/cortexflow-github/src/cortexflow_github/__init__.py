"""cortexflow-github — example CortexFlow plugin: GitHub repo events."""

from cortexflow_github.plugin import GitHubPlugin
from cortexflow_github.tool import GitHubEventsTool

__all__ = ["GitHubEventsTool", "GitHubPlugin"]
__version__ = "0.1.0"
