"""Multi-agent orchestration for CortexFlow.

Provides a lightweight orchestration layer that routes tasks to named
:class:`AgentNode` instances based on task type, keyword matching, source
channel, and priority ordering — without requiring a separate process or
network hop.

Quick start::

    from cortexflow_ai.orchestrator import AgentOrchestrator, AgentNodeConfig, AgentTask

    orch = AgentOrchestrator()
    orch.register(AgentNodeConfig(
        name="code",
        description="Handles code generation and debugging",
        model_override="anthropic/claude-sonnet-5",
        task_types=["code_generation", "code_review"],
        priority=10,
    ))
    orch.register(AgentNodeConfig(
        name="research",
        description="Handles research and summarisation tasks",
        model_override="google/gemini-flash",
        task_types=["summarization", "research"],
        routing_keywords=["research", "summarize", "explain"],
    ))

    task = AgentTask(content="Write a Python sort", task_type="code_generation")
    node = orch.select(task)   # → AgentNodeConfig(name="code", ...)
"""

from cortexflow_ai.orchestrator.node import AgentNode, AgentNodeConfig
from cortexflow_ai.orchestrator.orchestrator import AgentOrchestrator
from cortexflow_ai.orchestrator.task import AgentResult, AgentTask

__all__ = [
    "AgentNode",
    "AgentNodeConfig",
    "AgentOrchestrator",
    "AgentResult",
    "AgentTask",
]
