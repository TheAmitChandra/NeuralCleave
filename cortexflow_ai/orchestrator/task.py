"""AgentTask and AgentResult — the data contracts for inter-agent routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Task types understood by the orchestrator's routing engine.
# Mirrors the values in cortexflow_ai.agent.pipeline.INTENT_TASK_MAP plus extras.
KNOWN_TASK_TYPES: frozenset[str] = frozenset(
    {
        "general",
        "code_generation",
        "code_review",
        "summarization",
        "research",
        "creative",
        "task_decomposition",
        "reflection",
        "cheap_inference",
        "complex_reasoning",
        "translation",
        "data_analysis",
    }
)


@dataclass
class AgentTask:
    """Describes a unit of work to be routed to an agent node.

    Args:
        content:        The user's message or task description.
        session_id:     Identifies the conversation session.
        task_type:      Semantic category of the task (see :data:`KNOWN_TASK_TYPES`).
                        Defaults to ``"general"``.
        source_channel: Name of the originating channel adapter (e.g. ``"slack"``).
                        Used for channel-based routing rules.
        metadata:       Arbitrary key/value pairs forwarded to the selected node.
        timeout:        Per-task timeout in seconds.
    """

    content: str
    session_id: str = ""
    task_type: str = "general"
    source_channel: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("AgentTask.content must not be empty")
        if self.timeout <= 0:
            raise ValueError("AgentTask.timeout must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "session_id": self.session_id,
            "task_type": self.task_type,
            "source_channel": self.source_channel,
            "metadata": self.metadata,
            "timeout": self.timeout,
        }


@dataclass
class AgentResult:
    """Output produced by an agent node after processing a task.

    Args:
        content:    The generated response text.
        node_name:  Name of the node that handled the task.
        task_type:  The effective task type (may differ from :attr:`AgentTask.task_type`
                    if the node overrode it).
        latency_ms: Wall-clock time from dispatch to result in milliseconds.
        metadata:   Optional extra data from the node (model name, token usage, etc.).
    """

    content: str
    node_name: str
    task_type: str
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "node_name": self.node_name,
            "task_type": self.task_type,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }
