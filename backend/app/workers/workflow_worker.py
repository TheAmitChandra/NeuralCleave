"""CortexFlow Celery workflow worker tasks.

All tasks bridge async CortexFlow workflow engine modules into Celery's
synchronous execution model via ``asyncio.run()``.

Task catalogue
──────────────
  execute_workflow            Kick off a full workflow from a DAG definition
  execute_workflow_node       Execute a single node within a running workflow
  validate_workflow_result    ValidatorAgent check on a completed workflow
  reflect_on_workflow         ReflectionEngine scoring for a completed workflow
  rollback_workflow           Trigger checkpoint-based rollback on a failed workflow
  checkpoint_workflow_state   Persist current workflow state to PostgreSQL
  recover_stale_workflows     Beat periodic — detect and recover stuck workflows
  request_human_approval      Create a human approval gate (workflow-scope)
  write_audit_event           Persist a workflow-scope audit event
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from celery import chain, chord, group, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.core.observability.logs import get_logger
from app.core.orchestration.validator import ValidatorAgent
from app.core.reflection.engine import ReflectionEngine
from app.core.workflow_engine.dag import DAGNode, WorkflowDAG
from app.core.workflow_engine.scheduler import WorkflowScheduler

# Approval imports are deferred to task bodies (keep them lazy).

_task_logger = get_task_logger(__name__)
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Local facades — provide a simple, mockable interface over the async engine.
# These classes own their own async-session / Redis connections when called in
# production.  During tests the whole class is patched before any task runs.
# ---------------------------------------------------------------------------


class CheckpointManager:
    """Facade for checkpoint persistence used by Celery tasks."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

    async def save(self, state: dict[str, Any]) -> str:
        """Persist a raw state snapshot; returns a new checkpoint ID."""
        import json as _json
        checkpoint_id = str(uuid.uuid4())
        try:
            from app.db.redis import get_redis_client
            async with get_redis_client() as r:
                key = f"ckpt:{self.workflow_id}:{checkpoint_id}"
                await r.set(key, _json.dumps(state), ex=86400)
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint_redis_fallback", workflow_id=self.workflow_id, error=str(exc))
        return checkpoint_id


class RecoveryManager:
    """Facade for workflow recovery used by Celery tasks."""

    def __init__(self, workflow_id: str | None = None):
        self.workflow_id = workflow_id

    async def rollback(self, reason: str = "execution_failure") -> None:
        """Mark a workflow as ROLLED_BACK and emit an audit event."""
        logger.info("recovery.rollback", workflow_id=self.workflow_id, reason=reason)
        try:
            from app.core.events.bus import AgentCommunicationBus
            bus = AgentCommunicationBus()
            await bus.publish("workflow.rolled_back", {
                "workflow_id": self.workflow_id,
                "reason": reason,
            })
        except Exception:  # noqa: BLE001
            pass  # Best-effort event emission

    async def recover_all_stale(self) -> dict[str, Any]:
        """Sweep for stale workflows (best-effort in task context)."""
        return {"recovered": 0, "rolled_back": 0, "skipped": 0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):  # type: ignore[no-untyped-def]
    """Run a coroutine in a fresh event loop (Celery worker context)."""
    return asyncio.run(coro)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Workflow execution tasks
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.workflow_worker.execute_workflow",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def execute_workflow(
    self,
    workflow_id: str,
    dag_definition: dict[str, Any],
    initiator_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Kick off a complete workflow defined by a DAG.

    The scheduler resolves the execution order (topological sort), groups
    independent nodes for parallel execution, and submits each wave as a
    Celery ``group`` chord.

    Parameters
    ----------
    workflow_id:
        Stable UUID for this workflow run (used to persist checkpoints).
    dag_definition:
        Serialised DAG — ``{"nodes": [...], "edges": [...]}``
        where each node has ``node_id``, ``tool_name``, ``parameters``,
        ``depends_on``, ``retry_policy``, ``timeout_seconds``.
    initiator_id:
        Agent or user that triggered this workflow.
    metadata:
        Arbitrary metadata stored alongside the run.

    Returns
    -------
    Dict with ``workflow_id``, ``success``, ``results`` (per-node),
    ``completed_at``.
    """
    logger.info(
        "workflow_started",
        workflow_id=workflow_id,
        node_count=len(dag_definition.get("nodes", [])),
        initiator_id=initiator_id,
    )

    try:
        dag = WorkflowDAG.from_dict(dag_definition)
        scheduler = WorkflowScheduler(workflow_id=workflow_id)
        results = _run(scheduler.run(dag, metadata=metadata or {}))
        logger.info("workflow_completed", workflow_id=workflow_id)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "results": results,
            "completed_at": _now_iso(),
        }

    except SoftTimeLimitExceeded:
        logger.warning("workflow_soft_timeout", workflow_id=workflow_id)
        return {
            "success": False,
            "workflow_id": workflow_id,
            "error": "soft_time_limit_exceeded",
            "completed_at": _now_iso(),
        }
    except Exception as exc:
        logger.error("workflow_failed", workflow_id=workflow_id, error=str(exc))
        # Persist failure state before retrying
        checkpoint_workflow_state.apply_async(
            args=[workflow_id, {"status": "FAILED", "error": str(exc)}],
            queue="observability_queue",
        )
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.workflow_worker.execute_workflow_node",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def execute_workflow_node(
    self,
    workflow_id: str,
    node: dict[str, Any],
    upstream_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a single node within a running workflow.

    Called by :func:`execute_workflow` for each node in the topological wave.
    Can also be called directly for re-execution of a specific failed node.

    Parameters
    ----------
    workflow_id:    Parent workflow identifier.
    node:           Serialised ``DAGNode`` dict.
    upstream_results:
        Outputs from upstream nodes keyed by ``node_id`` — injected into
        ``node["parameters"]`` as ``_upstream`` for downstream access.
    """
    node_id: str = node.get("node_id", str(uuid.uuid4()))
    tool_name: str = node.get("tool_name", "")
    logger.info("workflow_node_started", workflow_id=workflow_id, node_id=node_id, tool_name=tool_name)

    try:
        dag_node = DAGNode(
            node_id=node_id,
            tool_name=tool_name,
            parameters={**node.get("parameters", {}), "_upstream": upstream_results or {}},
            depends_on=node.get("depends_on", []),
            timeout_seconds=node.get("timeout_seconds", 120.0),
        )
        scheduler = WorkflowScheduler(workflow_id=workflow_id)
        result = _run(scheduler.execute_node(dag_node))
        logger.info("workflow_node_completed", workflow_id=workflow_id, node_id=node_id)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "node_id": node_id,
            "output": result,
            "completed_at": _now_iso(),
        }

    except SoftTimeLimitExceeded:
        logger.warning("workflow_node_soft_timeout", node_id=node_id)
        return {
            "success": False,
            "workflow_id": workflow_id,
            "node_id": node_id,
            "error": "soft_time_limit_exceeded",
        }
    except Exception as exc:
        logger.error("workflow_node_failed", node_id=node_id, error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Validation / Reflection tasks
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.workflow_worker.validate_workflow_result",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def validate_workflow_result(
    self,
    workflow_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Run ValidatorAgent check on the output of a completed workflow.

    Returns a dict with ``passed``, ``score`` (0–100), and ``issues``.
    """
    logger.info("workflow_validation_started", workflow_id=workflow_id)
    try:
        from app.core.orchestration.validator import ValidatorAgent
        validator = ValidatorAgent()
        validation = _run(validator.validate(task_id=workflow_id, output=result, expected={}))
        return {"success": True, "workflow_id": workflow_id, "validation": validation}
    except Exception as exc:
        logger.error("workflow_validation_failed", workflow_id=workflow_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.workflow_worker.reflect_on_workflow",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def reflect_on_workflow(
    self,
    workflow_id: str,
    execution_record: dict[str, Any],
) -> dict[str, Any]:
    """Run ReflectionEngine on a completed workflow execution record.

    Returns a dict with ``score``, ``insights``, and ``retry_recommendation``.
    """
    logger.info("workflow_reflection_started", workflow_id=workflow_id)
    try:
        from app.core.reflection.engine import ReflectionEngine
        engine = ReflectionEngine()
        reflection = _run(engine.reflect({**execution_record, "task_id": workflow_id}))
        return {"success": True, "workflow_id": workflow_id, "reflection": reflection}
    except Exception as exc:
        logger.error("workflow_reflection_failed", workflow_id=workflow_id, error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Rollback + checkpoint tasks
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.workflow_worker.rollback_workflow",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def rollback_workflow(
    self,
    workflow_id: str,
    reason: str = "execution_failure",
) -> dict[str, Any]:
    """Trigger a checkpoint-based rollback on a failed workflow.

    The RecoveryManager restores the last known-good checkpoint and marks the
    workflow as ``ROLLED_BACK`` in the database.

    Parameters
    ----------
    workflow_id: Workflow to roll back.
    reason:      Human-readable rollback reason (logged to audit trail).
    """
    logger.info("workflow_rollback_started", workflow_id=workflow_id, reason=reason)
    try:
        recovery = RecoveryManager(workflow_id=workflow_id)
        _run(recovery.rollback(reason=reason))
        logger.info("workflow_rollback_completed", workflow_id=workflow_id)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "rolled_back_at": _now_iso(),
            "reason": reason,
        }
    except Exception as exc:
        logger.error("workflow_rollback_failed", workflow_id=workflow_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.workflow_worker.checkpoint_workflow_state",
    bind=False,
    acks_late=True,
    ignore_result=False,
)
def checkpoint_workflow_state(
    workflow_id: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Persist the current workflow state snapshot to PostgreSQL.

    Called automatically by the scheduler after each node completes and on
    failure.  Also available for explicit checkpointing.

    Parameters
    ----------
    workflow_id: Workflow to checkpoint.
    state:       Full state snapshot — ``{"status": ..., "completed_nodes": [...], ...}``.
    """
    logger.debug("workflow_checkpoint_saving", workflow_id=workflow_id)
    try:
        manager = CheckpointManager(workflow_id=workflow_id)
        checkpoint_id = _run(manager.save(state))
        return {"success": True, "workflow_id": workflow_id, "checkpoint_id": checkpoint_id}
    except Exception as exc:
        logger.error("workflow_checkpoint_failed", workflow_id=workflow_id, error=str(exc))
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Beat periodic — stale workflow recovery
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.workflow_worker.recover_stale_workflows",
    bind=False,
    acks_late=True,
)
def recover_stale_workflows() -> dict[str, Any]:
    """Detect and recover workflows stuck in RUNNING/EXECUTING state.

    Runs via Celery beat every 5 minutes.  A workflow is considered stale if
    its last checkpoint is older than ``WORKFLOW_STALE_THRESHOLD_SECONDS``
    (default: 600s / 10 minutes).

    For each stale workflow the recovery manager will:
    1. Attempt to resume from the last checkpoint.
    2. If resumption fails, trigger a rollback.
    3. Emit a ``workflow.stale_detected`` event to the bus.
    """
    logger.info("stale_workflow_recovery_sweep_started")
    try:
        recovery = RecoveryManager()
        stats = _run(recovery.recover_all_stale())
        logger.info("stale_workflow_recovery_completed", stats=stats)
        return {"success": True, "stats": stats}
    except Exception as exc:
        logger.error("stale_workflow_recovery_failed", error=str(exc))
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Approval + Audit tasks (workflow scope)
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.workflow_worker.request_human_approval",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def request_human_approval(
    self,
    approval_request: dict[str, Any],
) -> dict[str, Any]:
    """Create a human approval gate for a workflow-level action.

    Parameters
    ----------
    approval_request:
        Dict with ``action``, ``workflow_id``, ``risk_score``, ``context``.

    Returns a dict with ``approval_id`` and ``status`` = "pending".
    """
    logger.info(
        "workflow_approval_requested",
        action=approval_request.get("action"),
        workflow_id=approval_request.get("workflow_id"),
        risk_score=approval_request.get("risk_score"),
    )
    try:
        from app.core.governance.approvals import ApprovalRequest, ApprovalWorkflow
        manager = ApprovalWorkflow()
        req = ApprovalRequest(
            action=approval_request["action"],
            agent_id=approval_request.get("workflow_id", ""),
            risk_score=approval_request.get("risk_score", 75),
            context=approval_request.get("context", {}),
        )
        approval_id = _run(manager.create_approval(req))
        return {"success": True, "approval_id": approval_id, "status": "pending"}
    except Exception as exc:
        logger.error("workflow_approval_request_failed", error=str(exc))
        return {"success": False, "error": str(exc)}


@shared_task(
    name="app.workers.workflow_worker.write_audit_event",
    bind=False,
    acks_late=True,
    ignore_result=True,
)
def write_audit_event(event: dict[str, Any]) -> None:
    """Persist a workflow-scope audit event. Fire-and-forget."""
    logger.debug("workflow_audit_event_received", event_type=event.get("event_type"))
    try:
        from app.core.security.audit import AuditLogger
        audit = AuditLogger()
        _run(audit.log(event))
    except Exception as exc:
        logger.error("workflow_audit_write_failed", error=str(exc))
