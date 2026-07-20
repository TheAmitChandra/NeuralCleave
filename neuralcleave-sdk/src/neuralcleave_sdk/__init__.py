"""neuralcleave-sdk — typed interfaces for building NeuralCleave plugins.

Install this package (not the full ``NeuralCleave`` gateway) to write a
plugin, tool, or channel adapter that NeuralCleave can load::

    pip install neuralcleave-sdk

Then subclass one of:

    Plugin          — the entry point every plugin package registers
    Tool            — a discrete capability the agent can invoke
    ChannelAdapter  — a messaging platform integration

See https://github.com/TheAmitChandra/NeuralCleave for the full gateway
and plugin-loading documentation.
"""

from neuralcleave_sdk.channels import (
    Attachment,
    ChannelAdapter,
    InboundMessage,
    MessageHandler,
)
from neuralcleave_sdk.plugins import Plugin, PluginMetadata
from neuralcleave_sdk.tools import Tool, ToolResult

__all__ = [
    "Attachment",
    "ChannelAdapter",
    "InboundMessage",
    "MessageHandler",
    "Plugin",
    "PluginMetadata",
    "Tool",
    "ToolResult",
]

__version__ = "0.1.0"
