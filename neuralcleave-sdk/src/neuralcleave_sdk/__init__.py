"""cortexflow-sdk — typed interfaces for building CortexFlow plugins.

Install this package (not the full ``cortexflow`` gateway) to write a
plugin, tool, or channel adapter that CortexFlow can load::

    pip install cortexflow-sdk

Then subclass one of:

    Plugin          — the entry point every plugin package registers
    Tool            — a discrete capability the agent can invoke
    ChannelAdapter  — a messaging platform integration

See https://github.com/TheAmitChandra/CortexFlow for the full gateway
and plugin-loading documentation.
"""

from cortexflow_sdk.channels import (
    Attachment,
    ChannelAdapter,
    InboundMessage,
    MessageHandler,
)
from cortexflow_sdk.plugins import Plugin, PluginMetadata
from cortexflow_sdk.tools import Tool, ToolResult

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
