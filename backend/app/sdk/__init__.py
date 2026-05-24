"""CortexFlow Plugin & SDK — Public API.

This package provides a stable public interface for extending CortexFlow with
custom tools and agents without touching internal implementation details.

Quick start::

    from app.sdk import sdk_tool, AgentSDK, ToolDefinition

    @sdk_tool(
        name="my_tool",
        description="Does something useful",
        permissions=["file.read"],
        risk_level="low",
    )
    async def my_tool(parameters: dict) -> dict:
        ...

    class MyAgent(AgentSDK):
        agent_type = "my_agent"
        async def handle_task(self, task_payload: dict) -> dict:
            ...

Symbols re-exported here are considered part of the public SDK surface and
have backwards-compatibility guarantees within a major version.
"""

from __future__ import annotations

from app.sdk.tool_sdk import ToolSDK, sdk_tool, register_tool
from app.sdk.agent_sdk import AgentSDK
from app.sdk.memory_sdk import MemoryBackendSDK, MemoryRecord, MemoryRegistry
from app.sdk.event_sdk import EventSDK, on_event, TriggerSDK
from app.sdk.workflow_sdk import WorkflowStepSDK, WorkflowStepRegistry, workflow_step

# Also re-export the data models that SDK users need
from app.core.tools.registry import ToolDefinition, ToolCallRequest, ToolCallResult

__all__ = [
    # Tool SDK
    "ToolSDK",
    "sdk_tool",
    "register_tool",
    # Agent SDK
    "AgentSDK",
    # Memory SDK
    "MemoryBackendSDK",
    "MemoryRecord",
    "MemoryRegistry",
    # Event SDK
    "EventSDK",
    "on_event",
    "TriggerSDK",
    # Workflow SDK
    "WorkflowStepSDK",
    "WorkflowStepRegistry",
    "workflow_step",
    # Data models
    "ToolDefinition",
    "ToolCallRequest",
    "ToolCallResult",
]
