"""Run routed tasks through the gateway pipeline with node-local memory."""

from __future__ import annotations

import uuid
from typing import Any

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.agent.session import Session
from neuralcleave.channels.base import InboundMessage
from neuralcleave.memory.retrieval import MemoryResult, RetrievalContext
from neuralcleave.orchestrator.memory import MemoryNamespaceStore
from neuralcleave.orchestrator.node import AgentNode
from neuralcleave.orchestrator.task import AgentTask


class NamespaceMemory:
    """Pipeline memory backed by the existing bounded, in-process namespace.

    No access to the personal assistant's cross-channel memory is granted.
    Clearing a namespace via REST therefore clears future routed context too.
    """

    def __init__(self, store: MemoryNamespaceStore) -> None:
        self.store = store

    async def retrieve(self, query: str, **kwargs: Any) -> RetrievalContext:
        entries = self.store.all_entries()[-kwargs.get("top_k", 8):]
        results = [MemoryResult(source="short_term", content=e.value) for e in entries]
        return RetrievalContext(results, sum(len(str(e.value)) // 4 for e in entries))

    async def store_short_term(self, key: str, value: Any, session_id: str | None = None) -> None:
        self.store.put(f"{session_id}:{uuid.uuid4().hex}", value)

    async def store_semantic(self, embedding: list[float], payload: dict[str, Any]) -> None:
        # The exchange is already stored above; this store has no vector index.
        return None


class TaskRouter:
    """Per-call routing view; never mutates the shared model router."""

    def __init__(self, router: Any, node: AgentNode, task: AgentTask) -> None:
        self.router, self.node, self.task = router, node, task

    async def generate(self, prompt: str, **kwargs: Any):
        if kwargs.get("task_type") != "intent_extraction":
            kwargs["task_type"] = self.task.task_type
            kwargs["model_override"] = self.node.config.model_override
            kwargs["channel_id"] = self.task.source_channel
        return await self.router.generate(prompt, **kwargs)


class PipelineExecutor:
    """Share live tools/workspace/reflection while isolating routed memory."""

    def __init__(self, template: CognitivePipeline) -> None:
        self.template = template

    async def __call__(self, node: AgentNode, task: AgentTask, store: MemoryNamespaceStore):
        pipeline = CognitivePipeline(
            router=TaskRouter(self.template._router, node, task),
            memory=NamespaceMemory(store),
            workspace=self.template._workspace,
            agent_name=node.name,
            reflection=self.template._reflection,
            tool_registry=self.template._tool_registry,
            max_tool_steps=self.template._max_tool_steps,
        )
        session = Session(f"orchestrator:{node.memory_namespace}", task.session_id or "default")
        message = InboundMessage(
            channel=task.source_channel or "orchestrator",
            sender_id=session.sender_id,
            sender_name=node.name,
            text=task.content,
        )
        try:
            return await pipeline.run(message, session)
        finally:
            await pipeline.drain()
