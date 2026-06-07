"""Workflow Checkpoints — persist and load DAG execution state in PostgreSQL.

Each checkpoint snapshot serialises the full ``WorkflowDAG`` (including
per-node ``status``, ``output``, and ``error`` fields) into the
``Workflow.checkpoint_data`` JSONB column.  This allows the recovery module
to resume execution from the last known-good state after a crash.

Schema contract (stored in ``Workflow.checkpoint_data``):
    {
        "schema_version": 1,
        "dag_id": "<uuid>",
        "saved_at_iso": "<iso8601>",
        "node_states": {
            "<node_id>": {
                "status": "COMPLETED" | "FAILED" | "PENDING" | ...,
                "output": <any>,
                "error": <str | null>
            }
        }
    }

Note: The full dag_definition (node graph) is stored separately in
``Workflow.dag_definition``.  The checkpoint only stores mutable runtime
state so that the definition remains immutable / auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workflow_engine.dag import NodeStatus, WorkflowDAG
from app.db.models.workflow import Workflow

logger = structlog.get_logger(__name__)

CHECKPOINT_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def build_checkpoint_snapshot(dag: WorkflowDAG) -> dict[str, Any]:
    """Build a checkpoint dict from the current in-memory DAG state."""
    node_states: dict[str, dict[str, Any]] = {}
    for node in dag.nodes:
        output = node.output
        # Ensure output is JSON-serialisable (clip large payloads)
        if isinstance(output, (dict, list, str, int, float, bool, type(None))):
            serialised_output = output
        else:
            serialised_output = str(output)[:4096]

        node_states[node.node_id] = {
            "status": node.status.value,
            "output": serialised_output,
            "error": node.error,
        }

    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "dag_id": dag.dag_id,
        "saved_at_iso": datetime.now(timezone.utc).isoformat(),
        "node_states": node_states,
    }


def restore_node_states(dag: WorkflowDAG, checkpoint: dict[str, Any]) -> None:
    """Apply a checkpoint snapshot back onto an in-memory DAG.

    Mutates node ``status``, ``output``, and ``error`` in-place.
    Skips node_ids present in the checkpoint but absent from the DAG
    (handles schema evolution / node removal between versions).
    """
    node_states: dict[str, dict[str, Any]] = checkpoint.get("node_states", {})
    for node_id, state in node_states.items():
        node = dag.get_node(node_id)
        if node is None:
            logger.warning(
                "checkpoint.restore.unknown_node",
                node_id=node_id,
            )
            continue
        try:
            node.status = NodeStatus(state["status"])
        except ValueError:
            logger.warning(
                "checkpoint.restore.unknown_status",
                node_id=node_id,
                raw_status=state.get("status"),
            )
        node.output = state.get("output")
        node.error = state.get("error")


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------


async def save_checkpoint(
    workflow_id: str | uuid.UUID,
    dag: WorkflowDAG,
    session: AsyncSession,
) -> None:
    """Persist the current DAG state as a checkpoint in the Workflow row.

    Uses a targeted UPDATE so we don't reload the entire row.
    Does NOT commit — the caller is responsible for the transaction.
    """
    snapshot = build_checkpoint_snapshot(dag)

    await session.execute(
        update(Workflow)
        .where(Workflow.id == _to_uuid(workflow_id))
        .values(
            checkpoint_data=snapshot,
            updated_at=datetime.now(timezone.utc),
        )
    )

    logger.info(
        "checkpoint.saved",
        workflow_id=str(workflow_id),
        dag_id=dag.dag_id,
        node_count=len(dag.nodes),
    )


async def load_checkpoint(
    workflow_id: str | uuid.UUID,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """Load the latest checkpoint for a workflow.

    Returns the raw snapshot dict, or ``None`` if no checkpoint exists.
    """
    result = await session.execute(
        select(Workflow.checkpoint_data).where(Workflow.id == _to_uuid(workflow_id))
    )
    row = result.scalar_one_or_none()

    if row is None:
        logger.info("checkpoint.not_found", workflow_id=str(workflow_id))
        return None

    schema_ver = row.get("schema_version", 0)
    if schema_ver != CHECKPOINT_SCHEMA_VERSION:
        logger.warning(
            "checkpoint.schema_mismatch",
            workflow_id=str(workflow_id),
            found=schema_ver,
            expected=CHECKPOINT_SCHEMA_VERSION,
        )

    logger.info(
        "checkpoint.loaded",
        workflow_id=str(workflow_id),
        dag_id=row.get("dag_id"),
        saved_at=row.get("saved_at_iso"),
    )
    return row


async def clear_checkpoint(
    workflow_id: str | uuid.UUID,
    session: AsyncSession,
) -> None:
    """Remove checkpoint data for a workflow (e.g. after successful completion)."""
    await session.execute(
        update(Workflow)
        .where(Workflow.id == _to_uuid(workflow_id))
        .values(checkpoint_data=None, updated_at=datetime.now(timezone.utc))
    )
    logger.info("checkpoint.cleared", workflow_id=str(workflow_id))


async def mark_workflow_status(
    workflow_id: str | uuid.UUID,
    status: str,
    session: AsyncSession,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Update the ``Workflow.status`` column and optional timestamps."""
    values: dict[str, Any] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if started_at is not None:
        values["started_at"] = started_at
    if completed_at is not None:
        values["completed_at"] = completed_at

    await session.execute(
        update(Workflow).where(Workflow.id == _to_uuid(workflow_id)).values(**values)
    )
    logger.info(
        "checkpoint.workflow_status_updated",
        workflow_id=str(workflow_id),
        status=status,
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
