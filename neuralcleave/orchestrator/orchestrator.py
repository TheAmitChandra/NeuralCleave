"""AgentOrchestrator — registry and routing engine for multi-agent task dispatch."""

from __future__ import annotations

import itertools
import logging
import time
from typing import Any

from neuralcleave.orchestrator.memory import MemoryNamespaceManager
from neuralcleave.orchestrator.node import AgentNode, AgentNodeConfig
from neuralcleave.orchestrator.task import AgentResult, AgentTask

logger = logging.getLogger(__name__)

# Sentinel used when no node matches — a built-in catch-all node config.
_FALLBACK_NAME = "__fallback__"


class NodeNotFoundError(KeyError):
    """Raised when a named node is not registered."""


class NoEligibleNodeError(RuntimeError):
    """Raised when no registered node can handle the given task."""


class AgentOrchestrator:
    """Registry and routing engine for named agent nodes.

    Nodes are registered with :meth:`register` and tasks are routed with
    :meth:`select` (returns the winning node config) or :meth:`route` (returns
    an :class:`~neuralcleave.orchestrator.task.AgentResult`). When constructed
    with a real ``router``, :meth:`route` generates an actual response via
    :meth:`~neuralcleave.models.router.ModelRouter.generate` using the
    selected node's ``model_override``. Without one, :meth:`route` falls back
    to a lightweight placeholder result — selection-only, no generation (the
    CLI's local, disconnected fallback path has no API keys to build a real
    router from, so it always gets this mode).

    Routing algorithm
    -----------------
    1. Filter to nodes where :meth:`~AgentNodeConfig.can_handle` returns ``True``.
    2. If no nodes match and a *fallback* node is registered, use it.
    3. If still none, raise :class:`NoEligibleNodeError`.
    4. Among eligible nodes, pick the one with the highest ``priority``.
    5. Tie-break by round-robin across equally-ranked eligible nodes.

    Args:
        fallback_config: Optional catch-all node used when no other node matches.
        router: Optional :class:`~neuralcleave.models.router.ModelRouter`.
                When given, :meth:`route` actually generates a response
                instead of returning a placeholder.
    """

    def __init__(
        self,
        fallback_config: AgentNodeConfig | None = None,
        memory_manager: MemoryNamespaceManager | None = None,
        router: Any = None,
    ) -> None:
        self._nodes: dict[str, AgentNode] = {}
        self._rr_counters: dict[str, itertools.count[int]] = {}
        self._rr_indices: dict[str, int] = {}
        self._total_routed: int = 0
        self._fallback: AgentNode | None = None
        self._memory_manager: MemoryNamespaceManager = (
            memory_manager if memory_manager is not None else MemoryNamespaceManager()
        )
        # Optional ModelRouter — when given, route() actually generates a
        # real response via node.config.model_override instead of its
        # previous hardcoded placeholder. None keeps route() a pure
        # node-selection stub (e.g. the CLI's local, disconnected fallback
        # path, which has no API keys to build a real router from).
        self._router = router

        if fallback_config is not None:
            self._set_fallback(fallback_config)

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def register(self, config: AgentNodeConfig) -> AgentNode:
        """Register or replace a node.

        Re-registering under the same name replaces the existing entry and
        resets its statistics.

        Returns:
            The newly created :class:`AgentNode`.
        """
        node = AgentNode(config)
        self._nodes[config.name] = node
        logger.debug("orchestrator.register name=%s priority=%d", config.name, config.priority)
        return node

    def remove(self, name: str) -> None:
        """Remove a node by name.

        Raises:
            NodeNotFoundError: If no node with that name is registered.
        """
        if name not in self._nodes:
            raise NodeNotFoundError(f"No node named {name!r} is registered")
        del self._nodes[name]
        logger.debug("orchestrator.remove name=%s", name)

    def get(self, name: str) -> AgentNode:
        """Return the node with *name*.

        Raises:
            NodeNotFoundError: If not found.
        """
        try:
            return self._nodes[name]
        except KeyError:
            raise NodeNotFoundError(f"No node named {name!r} is registered") from None

    def list_nodes(self) -> list[AgentNodeConfig]:
        """Return a snapshot of all registered node configs (excluding fallback)."""
        return [node.config for node in self._nodes.values()]

    def node_count(self) -> int:
        """Number of registered nodes (excluding the fallback)."""
        return len(self._nodes)

    def set_fallback(self, config: AgentNodeConfig) -> None:
        """Register or replace the catch-all fallback node."""
        self._set_fallback(config)

    def clear_fallback(self) -> None:
        """Remove the catch-all fallback node."""
        self._fallback = None

    def enable(self, name: str) -> None:
        """Enable a node so it participates in routing."""
        self.get(name).config.enabled = True

    def disable(self, name: str) -> None:
        """Disable a node so it is skipped during routing."""
        self.get(name).config.enabled = False

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def select(self, task: AgentTask) -> AgentNode:
        """Select the best node for *task* without executing it.

        Returns:
            The winning :class:`AgentNode`.

        Raises:
            NoEligibleNodeError: When no node (including fallback) can handle the task.
        """
        eligible = [n for n in self._nodes.values() if n.can_handle(task)]

        if not eligible:
            if self._fallback and self._fallback.can_handle(task):
                logger.debug(
                    "orchestrator.select fallback task_type=%s channel=%s",
                    task.task_type,
                    task.source_channel,
                )
                return self._fallback
            raise NoEligibleNodeError(
                f"No eligible node for task_type={task.task_type!r} "
                f"channel={task.source_channel!r}"
            )

        winner = self._pick_highest_priority(eligible, task)
        logger.debug(
            "orchestrator.select winner=%s task_type=%s",
            winner.name,
            task.task_type,
        )
        return winner

    async def route(self, task: AgentTask) -> AgentResult:
        """Select a node and return its :class:`AgentResult`.

        When this orchestrator was constructed with a ``router``, actually
        generates a response via :meth:`ModelRouter.generate` using the
        selected node's ``model_override`` — a generation failure produces
        an error-flagged result rather than raising, so a routing caller
        never crashes because one node's model is temporarily unavailable.
        Without a ``router``, returns a lightweight placeholder result
        (node selected, no text generated) — this only does node selection
        and statistics recording, it does not run the task through the full
        :class:`~neuralcleave.agent.pipeline.CognitivePipeline` (memory
        retrieval, reflection, tool calls); that remains a bigger, separate
        integration a future round may take on.

        Raises:
            NoEligibleNodeError: When no node can handle the task.
        """
        t0 = time.monotonic()
        node = self.select(task)

        metadata: dict[str, Any] = {
            "model_override": node.config.model_override,
            "memory_namespace": node.memory_namespace,
        }
        if self._router is not None:
            try:
                gen = await self._router.generate(
                    task.content,
                    task_type=task.task_type,
                    session_id=task.session_id,
                    model_override=node.config.model_override,
                )
                content = gen.text
                metadata["model"] = gen.model
                metadata["provider"] = gen.provider
                metadata["usage"] = gen.usage
            except Exception as exc:
                logger.error("orchestrator.route generation failed node=%s: %s", node.name, exc)
                content = f"[routing to {node.name} failed: {exc}]"
                metadata["error"] = str(exc)
        else:
            content = f"[routed to {node.name}]"

        latency = (time.monotonic() - t0) * 1000
        result = AgentResult(
            content=content,
            node_name=node.name,
            task_type=task.task_type,
            latency_ms=latency,
            metadata=metadata,
        )
        node.record_result(result)
        self._total_routed += 1
        return result

    def get_node_namespaces(self) -> dict[str, str]:
        """Return a mapping of node name → effective memory namespace."""
        return {name: node.memory_namespace for name, node in self._nodes.items()}

    def memory_for_node(self, name: str):
        """Return the :class:`~MemoryNamespaceStore` for a node by name.

        Raises:
            NodeNotFoundError: If the node is not registered.
        """
        node = self.get(name)
        return self._memory_manager.namespace(node.memory_namespace)

    def stats(self) -> dict[str, Any]:
        """Return aggregate routing statistics."""
        return {
            "total_routed": self._total_routed,
            "node_count": self.node_count(),
            "has_fallback": self._fallback is not None,
            "nodes": [n.stats() for n in self._nodes.values()],
            "namespaces": self.get_node_namespaces(),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_fallback(self, config: AgentNodeConfig) -> None:
        self._fallback = AgentNode(config)

    def _pick_highest_priority(
        self, eligible: list[AgentNode], task: AgentTask
    ) -> AgentNode:
        """Return the highest-priority node; round-robin within tied nodes."""
        max_priority = max(n.config.priority for n in eligible)
        top_tier = [n for n in eligible if n.config.priority == max_priority]

        if len(top_tier) == 1:
            return top_tier[0]

        # Round-robin among equally-ranked nodes keyed by the task_type so
        # different task types rotate independently.
        rr_key = f"{task.task_type}:{max_priority}"
        if rr_key not in self._rr_indices:
            self._rr_indices[rr_key] = 0
        idx = self._rr_indices[rr_key] % len(top_tier)
        self._rr_indices[rr_key] = idx + 1
        return top_tier[idx]
