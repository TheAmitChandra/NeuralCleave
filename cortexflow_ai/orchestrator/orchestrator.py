"""AgentOrchestrator — registry and routing engine for multi-agent task dispatch."""

from __future__ import annotations

import itertools
import logging
import time
from typing import Any

from cortexflow_ai.orchestrator.node import AgentNode, AgentNodeConfig
from cortexflow_ai.orchestrator.task import AgentResult, AgentTask

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
    a lightweight :class:`~cortexflow_ai.orchestrator.task.AgentResult` filled
    by the node's stub executor — useful when a real pipeline is not available).

    Routing algorithm
    -----------------
    1. Filter to nodes where :meth:`~AgentNodeConfig.can_handle` returns ``True``.
    2. If no nodes match and a *fallback* node is registered, use it.
    3. If still none, raise :class:`NoEligibleNodeError`.
    4. Among eligible nodes, pick the one with the highest ``priority``.
    5. Tie-break by round-robin across equally-ranked eligible nodes.

    Args:
        fallback_config: Optional catch-all node used when no other node matches.
    """

    def __init__(self, fallback_config: AgentNodeConfig | None = None) -> None:
        self._nodes: dict[str, AgentNode] = {}
        self._rr_counters: dict[str, itertools.count[int]] = {}
        self._rr_indices: dict[str, int] = {}
        self._total_routed: int = 0
        self._fallback: AgentNode | None = None

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
        """Select a node and return a stub :class:`AgentResult`.

        This method is intentionally lightweight — it selects the node, records
        statistics, and returns a placeholder result.  In a real deployment the
        caller would use :meth:`select` and run the task through the
        :class:`~cortexflow_ai.agent.pipeline.CognitivePipeline` with
        ``node.config.model_override``.

        Raises:
            NoEligibleNodeError: When no node can handle the task.
        """
        t0 = time.monotonic()
        node = self.select(task)
        latency = (time.monotonic() - t0) * 1000

        result = AgentResult(
            content=f"[routed to {node.name}]",
            node_name=node.name,
            task_type=task.task_type,
            latency_ms=latency,
            metadata={"model_override": node.config.model_override},
        )
        node.record_result(result)
        self._total_routed += 1
        return result

    def stats(self) -> dict[str, Any]:
        """Return aggregate routing statistics."""
        return {
            "total_routed": self._total_routed,
            "node_count": self.node_count(),
            "has_fallback": self._fallback is not None,
            "nodes": [n.stats() for n in self._nodes.values()],
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
