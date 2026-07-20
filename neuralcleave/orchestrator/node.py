"""AgentNodeConfig and AgentNode — configuration and runtime representation of a sub-agent."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from neuralcleave.orchestrator.task import AgentResult, AgentTask


@dataclass
class AgentNodeConfig:
    """Declarative configuration for a named agent node.

    A node is a logical sub-agent with its own model preference and a set of
    routing rules.  When :class:`~neuralcleave.orchestrator.orchestrator.AgentOrchestrator`
    receives a task it evaluates all registered nodes' rules and delegates to
    the best match.

    Args:
        name:             Unique node identifier.  Letters, digits, hyphens, and
                          underscores only.
        description:      Human-readable summary of what this node handles.
        model_override:   Model string in ``"provider/model"`` form passed to
                          :class:`~neuralcleave.models.router.ModelRouter`.
                          ``None`` means use the gateway's default model.
        task_types:       If non-empty the node only matches tasks whose
                          ``task_type`` is in this list.
        routing_keywords: Case-insensitive words/phrases that, if found in
                          ``AgentTask.content``, make this node eligible.
                          An empty list means the node is keyword-agnostic.
        channel_patterns: Glob-style patterns matched against
                          ``AgentTask.source_channel``.  ``"*"`` matches
                          anything.  Empty means channel-agnostic.
        priority:         Tie-breaker when multiple nodes match — higher wins.
        max_concurrent:   Maximum number of simultaneous tasks this node will
                          accept (informational; not enforced by the orchestrator
                          itself, but available to callers).
        enabled:          When ``False`` the node is skipped during routing even
                          though it is registered.
    """

    name: str
    description: str = ""
    model_override: str | None = None
    task_types: list[str] = field(default_factory=list)
    routing_keywords: list[str] = field(default_factory=list)
    channel_patterns: list[str] = field(default_factory=list)
    priority: int = 0
    max_concurrent: int = 4
    enabled: bool = True
    memory_namespace: str = ""

    _NAME_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]+$")

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("AgentNodeConfig.name must not be empty")
        if not self._NAME_RE.match(self.name):
            raise ValueError(
                f"AgentNodeConfig.name {self.name!r} contains invalid characters; "
                "use letters, digits, hyphens, and underscores only"
            )
        if self.max_concurrent < 1:
            raise ValueError("AgentNodeConfig.max_concurrent must be >= 1")

    # ------------------------------------------------------------------
    # Routing predicates
    # ------------------------------------------------------------------

    def matches_task_type(self, task_type: str) -> bool:
        """Return ``True`` if this node handles *task_type* (or has no restriction)."""
        return not self.task_types or task_type in self.task_types

    def matches_keywords(self, content: str) -> bool:
        """Return ``True`` if *content* contains any routing keyword (or none set)."""
        if not self.routing_keywords:
            return True
        low = content.lower()
        return any(kw.lower() in low for kw in self.routing_keywords)

    def matches_channel(self, channel: str | None) -> bool:
        """Return ``True`` if *channel* matches any pattern (or none set)."""
        if not self.channel_patterns:
            return True
        if channel is None:
            return False
        return any(
            re.fullmatch(_glob_to_regex(pat), channel, re.IGNORECASE)
            for pat in self.channel_patterns
        )

    def can_handle(self, task: "AgentTask") -> bool:
        """Return ``True`` when all routing rules for this node match *task*."""
        if not self.enabled:
            return False
        return (
            self.matches_task_type(task.task_type)
            and self.matches_keywords(task.content)
            and self.matches_channel(task.source_channel)
        )

    @property
    def effective_memory_namespace(self) -> str:
        """Resolved namespace: explicit value, or the node's own name if unset."""
        return self.memory_namespace if self.memory_namespace else self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "model_override": self.model_override,
            "task_types": self.task_types,
            "routing_keywords": self.routing_keywords,
            "channel_patterns": self.channel_patterns,
            "priority": self.priority,
            "max_concurrent": self.max_concurrent,
            "enabled": self.enabled,
            "memory_namespace": self.memory_namespace,
            "effective_memory_namespace": self.effective_memory_namespace,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentNodeConfig":
        """Deserialise a dict (e.g. from the REST API) into an AgentNodeConfig."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            model_override=data.get("model_override"),
            task_types=list(data.get("task_types", [])),
            routing_keywords=list(data.get("routing_keywords", [])),
            channel_patterns=list(data.get("channel_patterns", [])),
            priority=int(data.get("priority", 0)),
            max_concurrent=int(data.get("max_concurrent", 4)),
            enabled=bool(data.get("enabled", True)),
            memory_namespace=str(data.get("memory_namespace", "")),
        )


def _glob_to_regex(pattern: str) -> str:
    """Convert a simple glob pattern (``*`` and ``?``) to a regex string."""
    return re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")


class AgentNode:
    """Runtime wrapper around an :class:`AgentNodeConfig`.

    Tracks per-node statistics and provides a lightweight synchronous
    ``execute`` method that callers can use when they want the node to
    produce a result directly (e.g. from a stub or test double) rather than
    delegating to the full :class:`~neuralcleave.agent.pipeline.CognitivePipeline`.

    In production, the orchestrator selects a node via
    :meth:`AgentOrchestrator.select` and the caller is responsible for running
    the task through the pipeline with the node's ``model_override``.
    """

    def __init__(self, config: AgentNodeConfig) -> None:
        self.config = config
        self._tasks_handled: int = 0
        self._total_latency_ms: float = 0.0
        self._errors: int = 0
        self._created_at: float = time.time()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def memory_namespace(self) -> str:
        """Effective memory namespace for this node."""
        return self.config.effective_memory_namespace

    def can_handle(self, task: AgentTask) -> bool:
        return self.config.can_handle(task)

    def record_result(self, result: AgentResult) -> None:
        """Update internal counters after a task completes."""
        self._tasks_handled += 1
        self._total_latency_ms += result.latency_ms

    def record_error(self) -> None:
        self._errors += 1

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.config.name,
            "tasks_handled": self._tasks_handled,
            "errors": self._errors,
            "avg_latency_ms": (
                self._total_latency_ms / self._tasks_handled
                if self._tasks_handled
                else 0.0
            ),
            "enabled": self.config.enabled,
        }
