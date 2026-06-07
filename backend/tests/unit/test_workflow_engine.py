"""Unit tests for the workflow engine (dag, scheduler, checkpoints, recovery).

All I/O (SQLAlchemy, Celery, Redis) is mocked.  Tests run fully offline.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.workflow_engine.checkpoints import (
    CHECKPOINT_SCHEMA_VERSION,
    build_checkpoint_snapshot,
    restore_node_states,
)
from app.core.workflow_engine.dag import (
    DAGNode,
    DAGValidationError,
    EdgeType,
    NodeStatus,
    WorkflowDAG,
)
from app.core.workflow_engine.scheduler import SchedulerResult, WorkflowScheduler

# ===========================================================================
# DAG model & algorithms
# ===========================================================================


class TestDAGModel:
    def _linear_dag(self) -> WorkflowDAG:
        """A → B → C"""
        dag = WorkflowDAG(dag_id="linear", name="linear")
        dag.add_node(DAGNode("A"))
        dag.add_node(DAGNode("B", depends_on=["A"]))
        dag.add_node(DAGNode("C", depends_on=["B"]))
        return dag

    def _diamond_dag(self) -> WorkflowDAG:
        """A → B, A → C, B → D, C → D"""
        dag = WorkflowDAG(dag_id="diamond", name="diamond")
        dag.add_node(DAGNode("A"))
        dag.add_node(DAGNode("B", depends_on=["A"]))
        dag.add_node(DAGNode("C", depends_on=["A"]))
        dag.add_node(DAGNode("D", depends_on=["B", "C"]))
        return dag

    # --- Basic structure ---

    def test_add_and_list_nodes(self):
        dag = WorkflowDAG()
        dag.add_node(DAGNode("x"))
        assert "x" in dag.node_ids

    def test_duplicate_node_raises(self):
        dag = WorkflowDAG()
        dag.add_node(DAGNode("x"))
        with pytest.raises(DAGValidationError, match="Duplicate"):
            dag.add_node(DAGNode("x"))

    def test_get_node_returns_none_for_unknown(self):
        dag = WorkflowDAG()
        assert dag.get_node("nope") is None

    # --- Validation ---

    def test_validate_linear_ok(self):
        dag = self._linear_dag()
        dag.validate()  # should not raise

    def test_validate_diamond_ok(self):
        dag = self._diamond_dag()
        dag.validate()  # should not raise

    def test_validate_cycle_raises(self):
        dag = WorkflowDAG()
        dag.add_node(DAGNode("A", depends_on=["B"]))
        dag.add_node(DAGNode("B", depends_on=["A"]))
        with pytest.raises(DAGValidationError, match="Cycle"):
            dag.validate()

    def test_validate_unknown_dependency_raises(self):
        dag = WorkflowDAG()
        dag.add_node(DAGNode("A", depends_on=["ghost"]))
        with pytest.raises(DAGValidationError, match="ghost"):
            dag.validate()

    # --- Topological sort ---

    def test_topo_sort_linear(self):
        dag = self._linear_dag()
        order = dag.topological_sort()
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_topo_sort_diamond(self):
        dag = self._diamond_dag()
        order = dag.topological_sort()
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    # --- Execution groups ---

    def test_execution_groups_linear(self):
        dag = self._linear_dag()
        groups = dag.execution_groups()
        assert groups == [["A"], ["B"], ["C"]]

    def test_execution_groups_diamond(self):
        dag = self._diamond_dag()
        groups = dag.execution_groups()
        assert groups[0] == ["A"]
        assert sorted(groups[1]) == ["B", "C"]
        assert groups[2] == ["D"]

    def test_execution_groups_single_node(self):
        dag = WorkflowDAG()
        dag.add_node(DAGNode("solo"))
        assert dag.execution_groups() == [["solo"]]

    def test_execution_groups_fully_parallel(self):
        """No dependencies — all nodes in one group."""
        dag = WorkflowDAG()
        dag.add_node(DAGNode("X"))
        dag.add_node(DAGNode("Y"))
        dag.add_node(DAGNode("Z"))
        groups = dag.execution_groups()
        assert len(groups) == 1
        assert sorted(groups[0]) == ["X", "Y", "Z"]

    # --- Critical path ---

    def test_critical_path_linear(self):
        dag = self._linear_dag()
        path, weight = dag.critical_path()
        assert path == ["A", "B", "C"]
        assert weight == 3.0

    def test_critical_path_diamond_equal_weights(self):
        dag = self._diamond_dag()
        _path, weight = dag.critical_path()
        assert weight == 3.0  # A(1) + B or C(1) + D(1)

    # --- Serialisation ---

    def test_round_trip_serialisation(self):
        dag = self._diamond_dag()
        data = dag.to_dict()
        dag2 = WorkflowDAG.from_dict(data)
        assert dag2.dag_id == dag.dag_id
        assert set(dag2.node_ids) == set(dag.node_ids)

    def test_from_dict_with_edge_types(self):
        dag = WorkflowDAG(dag_id="et-test")
        dag.add_node(DAGNode("A"))
        dag.add_node(
            DAGNode(
                "B",
                depends_on=["A"],
                edge_types={"A": EdgeType.FAILURE},
            )
        )
        data = dag.to_dict()
        dag2 = WorkflowDAG.from_dict(data)
        node_b = dag2.get_node("B")
        assert node_b is not None
        assert node_b.edge_types["A"] == EdgeType.FAILURE

    # --- Runtime helpers ---

    def test_pending_nodes_returns_ready_nodes(self):
        dag = self._linear_dag()
        dag._nodes["A"].status = NodeStatus.COMPLETED
        pending = dag.pending_nodes()
        assert "B" in pending
        assert "A" not in pending

    def test_is_complete_false_by_default(self):
        dag = self._linear_dag()
        assert dag.is_complete() is False

    def test_is_complete_true_when_all_terminal(self):
        dag = self._linear_dag()
        for node in dag.nodes:
            node.status = NodeStatus.COMPLETED
        assert dag.is_complete() is True

    def test_has_failure_false_initially(self):
        dag = self._linear_dag()
        assert dag.has_failure() is False

    def test_has_failure_true_on_failed_node(self):
        dag = self._linear_dag()
        dag._nodes["B"].status = NodeStatus.FAILED
        assert dag.has_failure() is True


# ===========================================================================
# Checkpoint snapshot helpers
# ===========================================================================


class TestCheckpointHelpers:
    def test_build_snapshot_schema_version(self):
        dag = WorkflowDAG(dag_id="snap-test")
        dag.add_node(DAGNode("X"))
        snap = build_checkpoint_snapshot(dag)
        assert snap["schema_version"] == CHECKPOINT_SCHEMA_VERSION

    def test_build_snapshot_captures_status(self):
        dag = WorkflowDAG(dag_id="snap-test")
        dag.add_node(DAGNode("X"))
        dag._nodes["X"].status = NodeStatus.COMPLETED
        dag._nodes["X"].output = {"result": 42}
        snap = build_checkpoint_snapshot(dag)
        assert snap["node_states"]["X"]["status"] == "COMPLETED"
        assert snap["node_states"]["X"]["output"] == {"result": 42}

    def test_restore_node_states_sets_fields(self):
        dag = WorkflowDAG(dag_id="restore-test")
        dag.add_node(DAGNode("A"))
        dag.add_node(DAGNode("B"))

        snap = {
            "schema_version": 1,
            "dag_id": "restore-test",
            "saved_at_iso": "2025-01-01T00:00:00+00:00",
            "node_states": {
                "A": {"status": "COMPLETED", "output": "ok", "error": None},
                "B": {"status": "FAILED", "output": None, "error": "timeout"},
            },
        }
        restore_node_states(dag, snap)
        assert dag._nodes["A"].status == NodeStatus.COMPLETED
        assert dag._nodes["B"].status == NodeStatus.FAILED
        assert dag._nodes["B"].error == "timeout"

    def test_restore_ignores_unknown_nodes(self):
        """Should not raise when checkpoint contains nodes not in current DAG."""
        dag = WorkflowDAG(dag_id="restore-test")
        dag.add_node(DAGNode("A"))
        snap = {
            "schema_version": 1,
            "dag_id": "restore-test",
            "saved_at_iso": "2025-01-01T00:00:00+00:00",
            "node_states": {
                "A": {"status": "COMPLETED", "output": None, "error": None},
                "ghost": {"status": "COMPLETED", "output": None, "error": None},
            },
        }
        restore_node_states(dag, snap)  # must not raise
        assert dag._nodes["A"].status == NodeStatus.COMPLETED

    def test_round_trip_snapshot(self):
        dag = WorkflowDAG(dag_id="rt-test")
        dag.add_node(DAGNode("X"))
        dag.add_node(DAGNode("Y", depends_on=["X"]))
        dag._nodes["X"].status = NodeStatus.COMPLETED
        dag._nodes["X"].output = [1, 2, 3]
        dag._nodes["Y"].status = NodeStatus.PENDING

        snap = build_checkpoint_snapshot(dag)
        dag2 = WorkflowDAG(dag_id="rt-test")
        dag2.add_node(DAGNode("X"))
        dag2.add_node(DAGNode("Y", depends_on=["X"]))
        restore_node_states(dag2, snap)

        assert dag2._nodes["X"].status == NodeStatus.COMPLETED
        assert dag2._nodes["X"].output == [1, 2, 3]
        assert dag2._nodes["Y"].status == NodeStatus.PENDING


# ===========================================================================
# Scheduler execution
# ===========================================================================


class TestWorkflowScheduler:
    """Tests for the async scheduler driving DAG execution."""

    @staticmethod
    async def _succeeding_executor(node: DAGNode) -> dict[str, Any]:
        return {"node_id": node.node_id, "ok": True}

    @staticmethod
    async def _failing_executor(node: DAGNode) -> None:
        raise RuntimeError(f"node {node.node_id} failed")

    def _make_scheduler(
        self, dag: WorkflowDAG, executor=None, *, max_retries_override: int | None = None
    ) -> WorkflowScheduler:
        if executor is None:
            executor = self._succeeding_executor
        if max_retries_override is not None:
            for node in dag.nodes:
                node.retry_policy["max_retries"] = max_retries_override
        return WorkflowScheduler(
            workflow_id=str(uuid.uuid4()),
            dag=dag,
            tool_executor=executor,
        )

    # --- Happy path ---

    @pytest.mark.asyncio
    async def test_linear_dag_runs_to_completion(self):
        dag = WorkflowDAG(dag_id="sched-linear")
        dag.add_node(DAGNode("A"))
        dag.add_node(DAGNode("B", depends_on=["A"]))
        scheduler = self._make_scheduler(dag)
        result = await scheduler.run()
        assert result.success is True
        assert result.failed_nodes == []
        assert dag._nodes["A"].status == NodeStatus.COMPLETED
        assert dag._nodes["B"].status == NodeStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_parallel_nodes_all_succeed(self):
        dag = WorkflowDAG(dag_id="parallel")
        dag.add_node(DAGNode("X"))
        dag.add_node(DAGNode("Y"))
        scheduler = self._make_scheduler(dag)
        result = await scheduler.run()
        assert result.success is True
        assert len(result.failed_nodes) == 0

    # --- Failure handling ---

    @pytest.mark.asyncio
    async def test_failing_node_marks_dag_failed(self):
        dag = WorkflowDAG(dag_id="fail-dag")
        dag.add_node(DAGNode("A", retry_policy={"max_retries": 0, "backoff_base_seconds": 0}))
        scheduler = self._make_scheduler(dag, executor=self._failing_executor)
        result = await scheduler.run()
        assert result.success is False
        assert "A" in result.failed_nodes

    @pytest.mark.asyncio
    async def test_failure_aborts_subsequent_groups(self):
        """Group 2 (B) should not run after Group 1 (A) fails."""
        dag = WorkflowDAG(dag_id="abort-dag")
        dag.add_node(DAGNode("A", retry_policy={"max_retries": 0, "backoff_base_seconds": 0}))
        dag.add_node(
            DAGNode(
                "B", depends_on=["A"], retry_policy={"max_retries": 0, "backoff_base_seconds": 0}
            )
        )

        call_log: list[str] = []

        async def tracked_executor(node: DAGNode) -> Any:
            call_log.append(node.node_id)
            if node.node_id == "A":
                raise RuntimeError("A exploded")
            return {}

        scheduler = self._make_scheduler(dag, executor=tracked_executor)
        result = await scheduler.run()
        assert result.success is False
        assert "A" in result.failed_nodes
        assert "B" not in call_log  # B must never run

    # --- Retry logic ---

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        attempts: dict[str, int] = {"A": 0}

        async def flaky_executor(node: DAGNode) -> Any:
            attempts[node.node_id] = attempts.get(node.node_id, 0) + 1
            if attempts[node.node_id] < 2:
                raise RuntimeError("transient error")
            return {"ok": True}

        dag = WorkflowDAG(dag_id="retry-dag")
        dag.add_node(DAGNode("A", retry_policy={"max_retries": 3, "backoff_base_seconds": 0}))
        scheduler = self._make_scheduler(dag, executor=flaky_executor)
        result = await scheduler.run()
        assert result.success is True
        assert attempts["A"] == 2

    # --- Checkpoint saver ---

    @pytest.mark.asyncio
    async def test_checkpoint_saver_called_after_each_group(self):
        dag = WorkflowDAG(dag_id="ckpt-dag")
        dag.add_node(DAGNode("A"))
        dag.add_node(DAGNode("B", depends_on=["A"]))

        checkpoint_calls: list[str] = []

        async def saver(wf_id: str, d: WorkflowDAG) -> None:
            checkpoint_calls.append(wf_id)

        scheduler = WorkflowScheduler(
            workflow_id="wf-ckpt",
            dag=dag,
            tool_executor=self._succeeding_executor,
            checkpoint_saver=saver,
        )
        await scheduler.run()
        # Two groups → two checkpoint saves
        assert len(checkpoint_calls) == 2

    # --- Celery plan ---

    def test_build_celery_plan_structure(self):
        dag = WorkflowDAG(dag_id="plan-dag")
        dag.add_node(DAGNode("A", tool_name="file.read"))
        dag.add_node(DAGNode("B", depends_on=["A"], tool_name="api.post"))
        scheduler = self._make_scheduler(dag)
        plan = scheduler.build_celery_plan()
        assert plan["workflow_id"] == scheduler.workflow_id
        assert len(plan["groups"]) == 2
        assert plan["groups"][0]["nodes"][0]["tool_name"] == "file.read"
        assert plan["groups"][1]["nodes"][0]["tool_name"] == "api.post"

    # --- Validation failure ---

    @pytest.mark.asyncio
    async def test_invalid_dag_returns_error_result(self):
        dag = WorkflowDAG(dag_id="bad-dag")
        dag.add_node(DAGNode("A", depends_on=["B"]))
        dag.add_node(DAGNode("B", depends_on=["A"]))  # cycle
        scheduler = self._make_scheduler(dag)
        result = await scheduler.run()
        assert result.success is False
        assert "validation" in (result.error or "").lower()
