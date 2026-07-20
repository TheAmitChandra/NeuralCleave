"""DAG — Directed Acyclic Graph definition and execution planning.

This module defines the data model for workflow DAGs and provides:
- Node/edge validation
- Cycle detection via Kahn's algorithm
- Topological sort
- Parallel execution groups (tasks with no unresolved dependencies run concurrently)
- Critical-path estimation
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"


class EdgeType(str, Enum):
    """How a downstream node waits on its upstream neighbour."""

    SUCCESS = "success"  # run only if upstream succeeded
    ALWAYS = "always"  # run regardless of upstream outcome
    FAILURE = "failure"  # run only if upstream failed (compensation / rollback)


@dataclass
class DAGNode:
    """Single unit of work in a workflow DAG.

    Attributes:
        node_id:        Stable identifier (matches a Task row's ID or a synthetic key).
        tool_name:      Tool registered in ToolRegistry to invoke, or None for sub-workflows.
        parameters:     Static input parameters passed to the tool handler.
        depends_on:     Upstream node_ids this node depends on (SUCCESS edges by default).
        retry_policy:   ``{"max_retries": int, "backoff_base_seconds": float}``.
        timeout_seconds: Hard timeout for this individual node.
        weight_seconds:  Estimated execution time for critical-path scheduling.
        metadata:       Free-form metadata stored alongside the node.
        status:         Runtime status (mutated by the scheduler).
        output:         Captured output after completion.
        error:          Captured error message on failure.
    """

    node_id: str
    tool_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    edge_types: dict[str, EdgeType] = field(default_factory=dict)  # {upstream_id: EdgeType}
    retry_policy: dict[str, Any] = field(
        default_factory=lambda: {
            "max_retries": 3,
            "backoff_base_seconds": 2.0,
        }
    )
    timeout_seconds: int = 300
    weight_seconds: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    # Runtime state — not serialised in the DAG definition
    status: NodeStatus = field(default=NodeStatus.PENDING, compare=False)
    output: Any = field(default=None, compare=False)
    error: str | None = field(default=None, compare=False)


@dataclass
class DAGEdge:
    """Explicit edge record.  Edges are also inferred from ``DAGNode.depends_on``."""

    source_id: str
    target_id: str
    edge_type: EdgeType = EdgeType.SUCCESS


class DAGValidationError(ValueError):
    """Raised when a DAG fails structural validation."""


class WorkflowDAG:
    """Directed Acyclic Graph for a NeuralCleave workflow.

    Usage::

        dag = WorkflowDAG(dag_id="wf-abc")
        dag.add_node(DAGNode("step1", tool_name="file.read", parameters={"path": "input.txt"}))
        dag.add_node(DAGNode("step2", tool_name="api.post", depends_on=["step1"]))
        dag.validate()
        groups = dag.execution_groups()  # [[step1], [step2]]
    """

    def __init__(self, dag_id: str | None = None, name: str = "") -> None:
        self.dag_id: str = dag_id or str(uuid.uuid4())
        self.name: str = name
        self._nodes: dict[str, DAGNode] = {}
        self._edges: list[DAGEdge] = []

    # ------------------------------------------------------------------
    # Build API
    # ------------------------------------------------------------------

    def add_node(self, node: DAGNode) -> None:
        if node.node_id in self._nodes:
            raise DAGValidationError(f"Duplicate node_id: {node.node_id!r}")
        self._nodes[node.node_id] = node

    def add_edge(
        self, source_id: str, target_id: str, edge_type: EdgeType = EdgeType.SUCCESS
    ) -> None:
        """Add an explicit edge (also registers in target node's depends_on)."""
        if source_id not in self._nodes:
            raise DAGValidationError(f"Source node not found: {source_id!r}")
        if target_id not in self._nodes:
            raise DAGValidationError(f"Target node not found: {target_id!r}")
        target = self._nodes[target_id]
        if source_id not in target.depends_on:
            target.depends_on.append(source_id)
        target.edge_types[source_id] = edge_type
        self._edges.append(DAGEdge(source_id, target_id, edge_type))

    def get_node(self, node_id: str) -> DAGNode | None:
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> list[DAGNode]:
        return list(self._nodes.values())

    @property
    def node_ids(self) -> list[str]:
        return list(self._nodes.keys())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Raise DAGValidationError if the graph is invalid."""
        self._check_unknown_dependencies()
        self._check_cycles()

    def _check_unknown_dependencies(self) -> None:
        for node in self._nodes.values():
            for dep_id in node.depends_on:
                if dep_id not in self._nodes:
                    raise DAGValidationError(
                        f"Node {node.node_id!r} depends on unknown node {dep_id!r}"
                    )

    def _check_cycles(self) -> None:
        """Kahn's algorithm — O(V+E).  Raises if a cycle is detected."""
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for node in self._nodes.values():
            for dep_id in node.depends_on:
                adjacency[dep_id].append(node.node_id)
                in_degree[node.node_id] += 1

        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited_count = 0

        while queue:
            nid = queue.popleft()
            visited_count += 1
            for child_id in adjacency[nid]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        if visited_count != len(self._nodes):
            raise DAGValidationError("Cycle detected in DAG — workflow cannot be executed")

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def topological_sort(self) -> list[str]:
        """Return node_ids in a valid execution order (dependencies before dependents).

        Ties are broken by insertion order (stable).
        """
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for node in self._nodes.values():
            for dep_id in node.depends_on:
                adjacency[dep_id].append(node.node_id)
                in_degree[node.node_id] += 1

        queue: deque[str] = deque(nid for nid in self._nodes if in_degree[nid] == 0)
        order: list[str] = []

        while queue:
            nid = queue.popleft()
            order.append(nid)
            for child_id in adjacency[nid]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        return order

    # ------------------------------------------------------------------
    # Parallel execution groups
    # ------------------------------------------------------------------

    def execution_groups(self) -> list[list[str]]:
        """Return layers of node_ids that can execute concurrently.

        Each inner list is a set of nodes that have no cross-dependencies
        within the same layer and can be dispatched in parallel.

        Example for A→C, B→C, C→D::

            groups == [["A", "B"], ["C"], ["D"]]
        """
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        adjacency: dict[str, list[str]] = defaultdict(list)

        for node in self._nodes.values():
            for dep_id in node.depends_on:
                adjacency[dep_id].append(node.node_id)
                in_degree[node.node_id] += 1

        groups: list[list[str]] = []
        current_layer = [nid for nid in self._nodes if in_degree[nid] == 0]

        while current_layer:
            groups.append(sorted(current_layer))  # stable output for tests
            next_layer: list[str] = []
            for nid in current_layer:
                for child_id in adjacency[nid]:
                    in_degree[child_id] -= 1
                    if in_degree[child_id] == 0:
                        next_layer.append(child_id)
            current_layer = next_layer

        return groups

    # ------------------------------------------------------------------
    # Critical path
    # ------------------------------------------------------------------

    def critical_path(self) -> tuple[list[str], float]:
        """Return (path_node_ids, total_weight_seconds) for the longest path."""
        order = self.topological_sort()
        dist: dict[str, float] = {nid: self._nodes[nid].weight_seconds for nid in order}
        prev: dict[str, str | None] = {nid: None for nid in order}

        for nid in order:
            node = self._nodes[nid]
            for dep_id in node.depends_on:
                candidate = dist[dep_id] + node.weight_seconds
                if candidate > dist[nid]:
                    dist[nid] = candidate
                    prev[nid] = dep_id

        if not dist:
            return [], 0.0

        end_node = max(dist, key=lambda k: dist[k])
        path: list[str] = []
        cur: str | None = end_node
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path, dist[end_node]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the JSON-compatible structure stored in Workflow.dag_definition."""
        return {
            "dag_id": self.dag_id,
            "name": self.name,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "tool_name": n.tool_name,
                    "parameters": n.parameters,
                    "depends_on": n.depends_on,
                    "edge_types": {k: v.value for k, v in n.edge_types.items()},
                    "retry_policy": n.retry_policy,
                    "timeout_seconds": n.timeout_seconds,
                    "weight_seconds": n.weight_seconds,
                    "metadata": n.metadata,
                }
                for n in self._nodes.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDAG":
        """Deserialise from a stored dag_definition dict."""
        dag = cls(dag_id=data.get("dag_id"), name=data.get("name", ""))
        for nd in data.get("nodes", []):
            node = DAGNode(
                node_id=nd["node_id"],
                tool_name=nd.get("tool_name"),
                parameters=nd.get("parameters", {}),
                depends_on=nd.get("depends_on", []),
                edge_types={k: EdgeType(v) for k, v in nd.get("edge_types", {}).items()},
                retry_policy=nd.get(
                    "retry_policy", {"max_retries": 3, "backoff_base_seconds": 2.0}
                ),
                timeout_seconds=nd.get("timeout_seconds", 300),
                weight_seconds=nd.get("weight_seconds", 1.0),
                metadata=nd.get("metadata", {}),
            )
            dag.add_node(node)
        return dag

    # ------------------------------------------------------------------
    # Runtime helpers
    # ------------------------------------------------------------------

    def pending_nodes(self) -> list[str]:
        """Return node_ids that are PENDING and whose dependencies have all completed."""
        completed = {
            nid for nid, node in self._nodes.items() if node.status == NodeStatus.COMPLETED
        }
        result = []
        for nid, node in self._nodes.items():
            if node.status != NodeStatus.PENDING:
                continue
            # Check only SUCCESS-type dependencies
            success_deps = [
                dep
                for dep in node.depends_on
                if node.edge_types.get(dep, EdgeType.SUCCESS) == EdgeType.SUCCESS
            ]
            if all(dep in completed for dep in success_deps):
                result.append(nid)
        return result

    def is_complete(self) -> bool:
        """True when all nodes are in a terminal state."""
        terminal = {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED}
        return all(n.status in terminal for n in self._nodes.values())

    def has_failure(self) -> bool:
        """True if any node has status FAILED."""
        return any(n.status == NodeStatus.FAILED for n in self._nodes.values())
