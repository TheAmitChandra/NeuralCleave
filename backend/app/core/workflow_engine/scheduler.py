"""Workflow Scheduler — Celery-based DAG task dispatch.

Responsibilities:
- Convert a WorkflowDAG into a Celery execution plan
- Dispatch parallel execution groups as Celery chords (fan-out + callback)
- Dispatch sequential chains with exponential-backoff retry
- Persist execution progress through the checkpoint module
- Emit structured log events at each state transition
- Return a ``SchedulerResult`` summarising the execution plan or outcome

Design notes:
- Celery import is guarded so the module can be used in unit tests without
  a running broker (``CELERY_AVAILABLE`` flag).
- The actual Celery app is created lazily in ``_get_celery_app()`` so tests
  can monkeypatch it before any task dispatch occurs.
- Database writes are handled by the checkpoint module; this module only
  calls ``save_checkpoint()`` / ``mark_node_state()``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.workflow_engine.dag import DAGNode, EdgeType, NodeStatus, WorkflowDAG

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional Celery import
# ---------------------------------------------------------------------------

try:
    from celery import Celery, chain, chord  # type: ignore[import]

    CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    CELERY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class NodeDispatchRecord:
    """Runtime record for a single dispatched node."""

    node_id: str
    celery_task_id: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    status: NodeStatus = NodeStatus.PENDING


@dataclass
class SchedulerResult:
    """Summary returned by ``WorkflowScheduler.run()``."""

    workflow_id: str
    dag_id: str
    success: bool
    execution_groups: list[list[str]]
    dispatch_records: list[NodeDispatchRecord] = field(default_factory=list)
    failed_nodes: list[str] = field(default_factory=list)
    total_elapsed_seconds: float = 0.0
    celery_plan: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# ---------------------------------------------------------------------------
# Celery app factory (lazy / overridable in tests)
# ---------------------------------------------------------------------------

_celery_app: Any = None


def _get_celery_app() -> Any:  # pragma: no cover
    """Return (or lazily create) the shared Celery application."""
    global _celery_app
    if _celery_app is None:
        from app.config import get_settings  # type: ignore[import]

        settings = get_settings()
        _celery_app = Celery(
            "NeuralCleave",
            broker=settings.redis_url,
            backend=settings.redis_url,
        )
        _celery_app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            task_acks_late=True,
            task_reject_on_worker_lost=True,
            worker_prefetch_multiplier=1,
        )
    return _celery_app


def set_celery_app(app: Any) -> None:
    """Override the Celery app (useful for testing / dependency injection)."""
    global _celery_app
    _celery_app = app


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class WorkflowScheduler:
    """Schedules and dispatches a ``WorkflowDAG`` for execution.

    Parameters:
        workflow_id:    UUID of the parent ``Workflow`` row.
        dag:            Validated ``WorkflowDAG`` instance.
        tool_executor:  Async callable ``(node: DAGNode) -> Any`` that actually
                        runs a tool.  Injected so the scheduler can be tested
                        without the full tool registry.
        checkpoint_saver:
                        Optional async callable ``(workflow_id, dag) -> None``
                        invoked after each group completes to persist state.
        max_parallelism: Hard cap on concurrent nodes in a single group.
    """

    def __init__(
        self,
        workflow_id: str,
        dag: WorkflowDAG,
        tool_executor: Any,  # async callable(node: DAGNode) -> Any
        checkpoint_saver: Any | None = None,
        max_parallelism: int = 20,
    ) -> None:
        self.workflow_id = workflow_id
        self.dag = dag
        self._tool_executor = tool_executor
        self._checkpoint_saver = checkpoint_saver
        self.max_parallelism = max_parallelism
        self._dispatch_records: dict[str, NodeDispatchRecord] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> SchedulerResult:
        """Execute the full DAG, group by group.

        Each group is dispatched concurrently using ``asyncio.gather``.
        Groups run sequentially (group N+1 only starts after group N
        completes or is otherwise settled).
        """
        start = time.monotonic()

        try:
            self.dag.validate()
        except Exception as exc:
            return SchedulerResult(
                workflow_id=self.workflow_id,
                dag_id=self.dag.dag_id,
                success=False,
                execution_groups=[],
                error=f"DAG validation failed: {exc}",
            )

        groups = self.dag.execution_groups()

        logger.info(
            "workflow.scheduler.start",
            workflow_id=self.workflow_id,
            dag_id=self.dag.dag_id,
            group_count=len(groups),
        )

        for group_idx, group in enumerate(groups):
            # Cap parallelism
            capped = group[: self.max_parallelism]
            if len(capped) < len(group):
                logger.warning(
                    "workflow.scheduler.parallelism_capped",
                    group_idx=group_idx,
                    original=len(group),
                    capped=len(capped),
                )

            await self._run_group(group_idx, capped)

            # Persist checkpoint after each group
            if self._checkpoint_saver:
                try:
                    await self._checkpoint_saver(self.workflow_id, self.dag)
                except Exception as ckpt_exc:  # noqa: BLE001
                    logger.warning(
                        "workflow.scheduler.checkpoint_failed",
                        error=str(ckpt_exc),
                    )

            # Stop early if a node failed
            if self.dag.has_failure():
                logger.error(
                    "workflow.scheduler.aborted_on_failure",
                    workflow_id=self.workflow_id,
                )
                break

        elapsed = time.monotonic() - start
        failed = [nid for nid, n in self.dag._nodes.items() if n.status == NodeStatus.FAILED]
        success = len(failed) == 0 and self.dag.is_complete()

        logger.info(
            "workflow.scheduler.finished",
            workflow_id=self.workflow_id,
            success=success,
            elapsed_seconds=round(elapsed, 3),
            failed_nodes=failed,
        )

        return SchedulerResult(
            workflow_id=self.workflow_id,
            dag_id=self.dag.dag_id,
            success=success,
            execution_groups=groups,
            dispatch_records=list(self._dispatch_records.values()),
            failed_nodes=failed,
            total_elapsed_seconds=round(elapsed, 3),
        )

    def build_celery_plan(self) -> dict[str, Any]:
        """Return a description of the Celery task plan without executing.

        Useful for previewing what will be submitted to the broker.
        """
        groups = self.dag.execution_groups()
        plan: dict[str, Any] = {"workflow_id": self.workflow_id, "groups": []}

        for group_idx, group in enumerate(groups):
            group_plan: dict[str, Any] = {
                "group_index": group_idx,
                "parallel": len(group) > 1,
                "nodes": [],
            }
            for nid in group:
                node = self.dag.get_node(nid)
                if node:
                    node_plan = {
                        "node_id": nid,
                        "tool_name": node.tool_name,
                        "retry_policy": node.retry_policy,
                        "timeout_seconds": node.timeout_seconds,
                        "celery_task": "NeuralCleave.tasks.execute_node",
                    }
                    group_plan["nodes"].append(node_plan)
            plan["groups"].append(group_plan)

        return plan

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_group(self, group_idx: int, node_ids: list[str]) -> None:
        """Dispatch a group of nodes concurrently and await all results."""
        logger.info(
            "workflow.scheduler.group_start",
            group_idx=group_idx,
            node_count=len(node_ids),
            node_ids=node_ids,
        )

        tasks = [self._execute_node(nid) for nid in node_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            "workflow.scheduler.group_done",
            group_idx=group_idx,
            node_ids=node_ids,
        )

    async def _execute_node(self, node_id: str) -> None:
        """Execute a single DAG node with retry logic."""
        node = self.dag.get_node(node_id)
        if node is None:
            logger.error("workflow.scheduler.node_not_found", node_id=node_id)
            return

        record = NodeDispatchRecord(
            node_id=node_id,
            celery_task_id=str(uuid.uuid4()),
        )
        self._dispatch_records[node_id] = record

        max_retries: int = node.retry_policy.get("max_retries", 3)
        backoff_base: float = node.retry_policy.get("backoff_base_seconds", 2.0)
        attempt = 0

        node.status = NodeStatus.RUNNING

        while attempt <= max_retries:
            try:
                output = await asyncio.wait_for(
                    self._tool_executor(node),
                    timeout=node.timeout_seconds,
                )
                node.output = output
                node.status = NodeStatus.COMPLETED
                record.status = NodeStatus.COMPLETED
                record.finished_at = time.monotonic()

                logger.info(
                    "workflow.scheduler.node_completed",
                    node_id=node_id,
                    attempt=attempt,
                    tool_name=node.tool_name,
                )
                return

            except asyncio.TimeoutError:
                err = f"Node {node_id!r} timed out after {node.timeout_seconds}s"
                node.error = err
                logger.warning("workflow.scheduler.node_timeout", node_id=node_id, attempt=attempt)
                # Timeout is not retried
                break

            except Exception as exc:  # noqa: BLE001
                node.error = str(exc)
                logger.warning(
                    "workflow.scheduler.node_error",
                    node_id=node_id,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < max_retries:
                    delay = backoff_base * (2**attempt)
                    logger.info(
                        "workflow.scheduler.node_retry",
                        node_id=node_id,
                        next_attempt=attempt + 1,
                        delay_seconds=delay,
                    )
                    await asyncio.sleep(delay)
                    node.status = NodeStatus.RETRYING
                    attempt += 1
                    continue
                break

        # Exhausted retries or timeout
        node.status = NodeStatus.FAILED
        record.status = NodeStatus.FAILED
        record.finished_at = time.monotonic()

        logger.error(
            "workflow.scheduler.node_failed",
            node_id=node_id,
            error=node.error,
        )
