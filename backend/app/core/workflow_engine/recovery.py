"""Workflow Recovery — resume DAG execution from the last checkpoint.

This module handles crash-recovery for workflows that were interrupted
before completion.  It loads the last persisted checkpoint, reconstructs
the ``WorkflowDAG`` from the stored ``dag_definition`` + runtime state,
re-creates a ``WorkflowScheduler`` configured to skip already-completed
nodes, and drives it to completion.

Recovery decision table:
    Workflow status  → Recovery action
    ─────────────────────────────────
    RUNNING          → Likely crashed.  Restore checkpoint and re-run.
    FAILED           → Do not auto-recover.  Caller must explicitly request.
    PAUSED           → Restore checkpoint and re-run from paused point.
    PENDING          → No checkpoint expected; run fresh.
    COMPLETED        → No action needed.  Return immediately.
    ROLLED_BACK      → No action needed.  Return immediately.

Usage::

    async with get_async_session() as session:
        result = await recover_workflow(
            workflow_id="...",
            tool_executor=my_executor,
            session=session,
        )
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workflow_engine.checkpoints import (
    build_checkpoint_snapshot,
    clear_checkpoint,
    load_checkpoint,
    mark_workflow_status,
    restore_node_states,
    save_checkpoint,
)
from app.core.workflow_engine.dag import NodeStatus, WorkflowDAG
from app.core.workflow_engine.scheduler import SchedulerResult, WorkflowScheduler
from app.db.models.workflow import Workflow

logger = structlog.get_logger(__name__)

# Statuses that are final — no recovery attempt is warranted.
_TERMINAL_STATUSES = frozenset({"COMPLETED", "ROLLED_BACK"})
# Statuses that allow automatic recovery.
_RECOVERABLE_STATUSES = frozenset({"RUNNING", "PAUSED"})


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

async def recover_workflow(
    workflow_id: str | uuid.UUID,
    tool_executor: Any,
    session: AsyncSession,
    *,
    force: bool = False,
) -> SchedulerResult | None:
    """Attempt to recover a workflow that did not complete cleanly.

    Parameters:
        workflow_id:    The ``Workflow.id`` to recover.
        tool_executor:  Async callable ``(node: DAGNode) -> Any`` injected into
                        the scheduler for actual tool execution.
        session:        SQLAlchemy async session (caller manages transaction).
        force:          If ``True``, attempt recovery even for FAILED workflows.

    Returns:
        ``SchedulerResult`` if recovery was run, ``None`` if no action was needed
        (workflow was already in a terminal state or not found).
    """
    wf_id = _to_uuid(workflow_id)

    # ---- Load the Workflow row ----
    result = await session.execute(select(Workflow).where(Workflow.id == wf_id))
    workflow: Workflow | None = result.scalar_one_or_none()

    if workflow is None:
        logger.warning("recovery.workflow_not_found", workflow_id=str(workflow_id))
        return None

    status = workflow.status

    logger.info(
        "recovery.started",
        workflow_id=str(workflow_id),
        current_status=status,
        force=force,
    )

    # ---- Terminal — nothing to do ----
    if status in _TERMINAL_STATUSES:
        logger.info("recovery.skipped_terminal", workflow_id=str(workflow_id), status=status)
        return None

    # ---- FAILED — only recover if forced ----
    if status == "FAILED" and not force:
        logger.info("recovery.skipped_failed", workflow_id=str(workflow_id))
        return None

    # ---- PENDING — no checkpoint; run fresh ----
    if status == "PENDING":
        logger.info("recovery.fresh_run", workflow_id=str(workflow_id))
        return await _run_fresh(workflow, tool_executor, session)

    # ---- RUNNING / PAUSED (or forced FAILED) — restore from checkpoint ----
    checkpoint = await load_checkpoint(wf_id, session)

    if checkpoint is None:
        # No checkpoint found — start fresh
        logger.warning(
            "recovery.no_checkpoint_found",
            workflow_id=str(workflow_id),
            status=status,
        )
        return await _run_fresh(workflow, tool_executor, session)

    return await _run_from_checkpoint(workflow, checkpoint, tool_executor, session)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _run_fresh(
    workflow: Workflow,
    tool_executor: Any,
    session: AsyncSession,
) -> SchedulerResult:
    """Reconstruct a DAG from dag_definition and run it from the start."""
    dag = WorkflowDAG.from_dict(workflow.dag_definition)

    await mark_workflow_status(
        workflow.id,
        "RUNNING",
        session,
        started_at=datetime.now(timezone.utc),
    )
    await session.commit()

    result = await _execute_dag(str(workflow.id), dag, tool_executor, session)

    final_status = "COMPLETED" if result.success else "FAILED"
    await mark_workflow_status(
        workflow.id,
        final_status,
        session,
        completed_at=datetime.now(timezone.utc),
    )
    if result.success:
        await clear_checkpoint(workflow.id, session)
    await session.commit()

    return result


async def _run_from_checkpoint(
    workflow: Workflow,
    checkpoint: dict[str, Any],
    tool_executor: Any,
    session: AsyncSession,
) -> SchedulerResult:
    """Restore DAG state from a checkpoint and resume execution."""
    dag = WorkflowDAG.from_dict(workflow.dag_definition)
    restore_node_states(dag, checkpoint)

    completed_count = sum(
        1 for n in dag.nodes if n.status == NodeStatus.COMPLETED
    )
    logger.info(
        "recovery.restored",
        workflow_id=str(workflow.id),
        completed_nodes=completed_count,
        total_nodes=len(dag.nodes),
    )

    # Mark workflow RUNNING again in case it was PAUSED
    await mark_workflow_status(workflow.id, "RUNNING", session)
    await session.commit()

    result = await _execute_dag(str(workflow.id), dag, tool_executor, session)

    final_status = "COMPLETED" if result.success else "FAILED"
    await mark_workflow_status(
        workflow.id,
        final_status,
        session,
        completed_at=datetime.now(timezone.utc),
    )
    if result.success:
        await clear_checkpoint(workflow.id, session)
    await session.commit()

    return result


async def _execute_dag(
    workflow_id: str,
    dag: WorkflowDAG,
    tool_executor: Any,
    session: AsyncSession,
) -> SchedulerResult:
    """Create a scheduler with a checkpoint saver wired to this session and run it."""

    async def _saver(wf_id: str, d: WorkflowDAG) -> None:
        await save_checkpoint(wf_id, d, session)
        await session.commit()

    scheduler = WorkflowScheduler(
        workflow_id=workflow_id,
        dag=dag,
        tool_executor=tool_executor,
        checkpoint_saver=_saver,
    )
    return await scheduler.run()


# ---------------------------------------------------------------------------
# Rollback helper
# ---------------------------------------------------------------------------

async def rollback_workflow(
    workflow_id: str | uuid.UUID,
    session: AsyncSession,
    *,
    rollback_executor: Any | None = None,
) -> None:
    """Mark a workflow as ROLLED_BACK and optionally run compensation nodes.

    Compensation nodes are DAG nodes whose ``edge_types`` includes a
    ``FAILURE`` edge pointing to them.  If ``rollback_executor`` is provided,
    those nodes are executed in reverse topological order.
    """
    wf_id = _to_uuid(workflow_id)

    result = await session.execute(select(Workflow).where(Workflow.id == wf_id))
    workflow: Workflow | None = result.scalar_one_or_none()

    if workflow is None:
        logger.warning("recovery.rollback.not_found", workflow_id=str(workflow_id))
        return

    if rollback_executor is not None:
        dag = WorkflowDAG.from_dict(workflow.dag_definition)
        checkpoint = await load_checkpoint(wf_id, session)
        if checkpoint:
            restore_node_states(dag, checkpoint)

        # Find failure-edge nodes (compensation tasks)
        compensation_ids = [
            node.node_id
            for node in dag.nodes
            if any(et.value == "failure" for et in node.edge_types.values())
        ]

        if compensation_ids:
            logger.info(
                "recovery.rollback.running_compensation",
                workflow_id=str(workflow_id),
                compensation_nodes=compensation_ids,
            )
            # Run compensation nodes in reverse topological order
            topo = dag.topological_sort()
            ordered_comp = [nid for nid in reversed(topo) if nid in compensation_ids]
            for nid in ordered_comp:
                node = dag.get_node(nid)
                if node:
                    try:
                        await rollback_executor(node)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "recovery.rollback.compensation_error",
                            node_id=nid,
                            error=str(exc),
                        )

    await mark_workflow_status(workflow_id, "ROLLED_BACK", session)
    await clear_checkpoint(wf_id, session)
    await session.commit()

    logger.info("recovery.rollback.completed", workflow_id=str(workflow_id))


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
