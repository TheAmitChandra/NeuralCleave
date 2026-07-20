"""NeuralCleave Celery agent worker tasks.

All tasks in this module run inside Celery worker processes.  They bridge the
async NeuralCleave core modules to Celery's synchronous task execution model via
``asyncio.run()``.

Task catalogue
──────────────
  run_agent_task              Execute a single AgentTask through the runtime
  dispatch_agent_action       Fire an immediate high-priority action on an agent
  terminate_agent             Gracefully stop a running agent
  decompose_task              Run PlannerAgent task decomposition
  validate_agent_output       Run ValidatorAgent on a completed task result
  critique_agent_output       Run CriticAgent quality review
  reflect_on_execution        Run ReflectionEngine on an execution result
  write_audit_event           Persist an audit event to the database
  request_human_approval      Create a human approval gate and pause execution
  update_behavioral_weights   Trigger the learning optimizer (nightly)
  prune_memory                Prune low-importance memory entries
  agent_heartbeat_sweep       Evaluate all running agents (beat periodic)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.core.agent_runtime.agent import AgentConfig, AgentRuntime, AgentTask
from app.core.governance.approvals import ApprovalRequest, ApprovalWorkflow
from app.core.learning.optimizer import BehaviorOptimizer
from app.core.observability.logs import get_logger
from app.core.orchestration.critic import CriticAgent
from app.core.orchestration.planner import PlannerAgent
from app.core.orchestration.validator import ValidatorAgent
from app.core.reflection.engine import ReflectionEngine

# Heavy DB-touching imports (AuditLogger, HeartbeatMonitor, MemoryRetrievalPipeline)
# are deferred to task bodies — they trigger get_settings() which requires env vars.

# Use structlog for all structured log calls; Celery task logger is kept for
# Celery internals only (it wraps standard Python logging).
_task_logger = get_task_logger(__name__)
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):  # type: ignore[no-untyped-def]
    """Run a coroutine in a fresh event loop (Celery worker context)."""
    return asyncio.run(coro)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Core agent execution tasks
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.agent_worker.run_agent_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def run_agent_task(self, task_payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a single AgentTask through the NeuralCleave cognitive pipeline.

    Parameters
    ----------
    task_payload:
        Must contain:
        - ``agent_id``    (str)
        - ``task_id``     (str)
        - ``description`` (str)
        - ``agent_type``  (str, optional — defaults to "generic")
        - ``metadata``    (dict, optional)
        - ``priority``    (int 0–10, optional)

    Returns a dict with ``success``, ``result``, ``agent_id``, ``task_id``.
    """
    agent_id: str = task_payload.get("agent_id", str(uuid.uuid4()))
    task_id: str = task_payload.get("task_id", str(uuid.uuid4()))
    description: str = task_payload.get("description", "")

    logger.info("agent_task_started [agent=%s task=%s]", agent_id, task_id)

    try:
        config = AgentConfig(
            name=f"agent-{agent_id[:8]}",
            agent_type=task_payload.get("agent_type", "generic"),
            task_timeout_seconds=task_payload.get("timeout_seconds", 300.0),
        )
        runtime = AgentRuntime(agent_id=agent_id, config=config)
        task = AgentTask(
            task_id=task_id,
            description=description,
            priority=task_payload.get("priority", 5),
            payload=task_payload.get("metadata", {}),
        )
        result = _run(runtime.execute_task(task))
        logger.info("agent_task_completed [agent=%s task=%s]", agent_id, task_id)
        return {
            "success": True,
            "agent_id": agent_id,
            "task_id": task_id,
            "result": result,
            "completed_at": _now_iso(),
        }

    except SoftTimeLimitExceeded:
        logger.warning("agent_task_soft_timeout [agent=%s task=%s]", agent_id, task_id)
        return {
            "success": False,
            "agent_id": agent_id,
            "task_id": task_id,
            "error": "soft_time_limit_exceeded",
            "completed_at": _now_iso(),
        }
    except Exception as exc:
        logger.error("agent_task_failed", agent_id=agent_id, task_id=task_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.agent_worker.dispatch_agent_action",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    acks_late=True,
)
def dispatch_agent_action(self, agent_id: str, action: dict[str, Any]) -> dict[str, Any]:
    """Fire an immediate high-priority action on an already-running agent.

    Parameters
    ----------
    agent_id:  Target agent's UUID string.
    action:    Action descriptor — must contain ``type`` and ``payload`` keys.
    """
    logger.info("agent_action_dispatched [agent=%s]", agent_id)
    try:
        config = AgentConfig(name=f"agent-{agent_id[:8]}")
        runtime = AgentRuntime(agent_id=agent_id, config=config)
        result = _run(runtime.handle_action(agent_id=agent_id, action=action))
        return {"success": True, "agent_id": agent_id, "result": result}
    except Exception as exc:
        logger.error("agent_action_failed", agent_id=agent_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.agent_worker.terminate_agent",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def terminate_agent(self, agent_id: str, reason: str = "user_request") -> dict[str, Any]:
    """Gracefully stop a running agent.

    Parameters
    ----------
    agent_id: Agent to terminate.
    reason:   Human-readable termination reason (logged to audit trail).
    """
    logger.info("agent_terminate_requested [agent=%s reason=%s]", agent_id, reason)
    try:
        config = AgentConfig(name=f"agent-{agent_id[:8]}")
        runtime = AgentRuntime(agent_id=agent_id, config=config)
        _run(runtime.terminate(reason=reason))
        return {"success": True, "agent_id": agent_id, "terminated_at": _now_iso()}
    except Exception as exc:
        logger.error("agent_terminate_failed", agent_id=agent_id, error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Planning task
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.agent_worker.decompose_task",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
)
def decompose_task(
    self, task_description: str, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run PlannerAgent to decompose a task description into a subtask DAG.

    Parameters
    ----------
    task_description: High-level task to decompose.
    context:          Optional agent/memory context to inform planning.

    Returns
    -------
    Dict containing ``subtasks`` list and ``dag`` adjacency dict.
    """
    logger.info("task_decomposition_started", description=task_description[:80])
    try:
        planner = PlannerAgent()
        plan = _run(planner.decompose(task_description, context=context or {}))
        return {"success": True, "plan": plan}
    except Exception as exc:
        logger.error("task_decomposition_failed", error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Validation / Critique / Reflection tasks
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.agent_worker.validate_agent_output",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    acks_late=True,
)
def validate_agent_output(
    self, task_id: str, output: dict[str, Any], expected: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run ValidatorAgent on a completed task output.

    Returns a dict with ``passed`` (bool), ``score`` (0–100), and ``issues``.
    """
    logger.info("validation_started", task_id=task_id)
    try:
        validator = ValidatorAgent()
        result = _run(validator.validate(task_id=task_id, output=output, expected=expected or {}))
        return {"success": True, "task_id": task_id, "validation": result}
    except Exception as exc:
        logger.error("validation_failed", task_id=task_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.agent_worker.critique_agent_output",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def critique_agent_output(self, task_id: str, output: dict[str, Any]) -> dict[str, Any]:
    """Run CriticAgent quality review on a completed task output.

    Returns a dict with ``quality_score`` (0–100), ``feedback``, and ``recommendation``.
    """
    logger.info("critique_started", task_id=task_id)
    try:
        critic = CriticAgent()
        result = _run(critic.review(task_id=task_id, output=output))
        return {"success": True, "task_id": task_id, "critique": result}
    except Exception as exc:
        logger.error("critique_failed", task_id=task_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.agent_worker.reflect_on_execution",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def reflect_on_execution(self, execution_record: dict[str, Any]) -> dict[str, Any]:
    """Run ReflectionEngine on a completed execution record.

    Parameters
    ----------
    execution_record:
        Must contain ``task_id``, ``agent_id``, ``output``, ``duration_ms``.

    Returns a dict with ``score``, ``insights``, and ``retry_recommendation``.
    """
    task_id = execution_record.get("task_id", "unknown")
    logger.info("reflection_started", task_id=task_id)
    try:
        engine = ReflectionEngine()
        result = _run(engine.reflect(execution_record))
        return {"success": True, "task_id": task_id, "reflection": result}
    except Exception as exc:
        logger.error("reflection_failed", task_id=task_id, error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Observability / Audit task
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.agent_worker.write_audit_event",
    bind=False,
    acks_late=True,
    ignore_result=True,
)
def write_audit_event(event: dict[str, Any]) -> None:
    """Persist an audit event to the audit_logs table.

    Fire-and-forget — result is not stored.  Failures are logged but not
    retried to avoid blocking the observability queue under pressure.

    Parameters
    ----------
    event:
        Dict with at minimum ``event_type`` and ``payload``.
        Optional keys: ``agent_id``, ``user_id``, ``workflow_id``, ``risk_score``.
    """
    logger.debug("audit_event_received", event_type=event.get("event_type"))
    try:
        from app.core.security.audit import AuditLogger

        audit = AuditLogger()
        _run(audit.log(event))
    except Exception as exc:
        logger.error("audit_event_write_failed", event_type=event.get("event_type"), error=str(exc))


# ---------------------------------------------------------------------------
# Approval task
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.agent_worker.request_human_approval",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def request_human_approval(
    self,
    approval_request: dict[str, Any],
) -> dict[str, Any]:
    """Create a human approval gate and pause the calling workflow.

    Parameters
    ----------
    approval_request:
        Dict with ``action``, ``agent_id``, ``risk_score``, ``context``.

    Returns a dict with ``approval_id`` and ``status`` = "pending".
    """
    logger.info(
        "approval_requested",
        action=approval_request.get("action"),
        agent_id=approval_request.get("agent_id"),
        risk_score=approval_request.get("risk_score"),
    )
    try:
        manager = ApprovalWorkflow()
        req = ApprovalRequest(
            action=approval_request["action"],
            agent_id=approval_request.get("agent_id", ""),
            risk_score=approval_request.get("risk_score", 75),
            context=approval_request.get("context", {}),
        )
        approval_id = _run(manager.create_approval(req))
        return {"success": True, "approval_id": approval_id, "status": "pending"}
    except Exception as exc:
        logger.error("approval_request_failed", error=str(exc))
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Background learning tasks
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.agent_worker.update_behavioral_weights",
    bind=False,
    acks_late=True,
)
def update_behavioral_weights() -> dict[str, Any]:
    """Nightly consolidation — update RL behavioral weights from feedback data.

    Runs via Celery beat at 02:00 UTC.  Reads the previous 24h of feedback
    records, computes reward signals, and updates per-agent strategy weights.
    """
    logger.info("behavioral_weight_update_started")
    try:
        optimizer = BehaviorOptimizer()
        stats = _run(optimizer.consolidate_daily())
        logger.info("behavioral_weight_update_completed", stats=stats)
        return {"success": True, "stats": stats}
    except Exception as exc:
        logger.error("behavioral_weight_update_failed", error=str(exc))
        return {"success": False, "error": str(exc)}


@shared_task(
    name="app.workers.agent_worker.prune_memory",
    bind=False,
    acks_late=True,
)
def prune_memory() -> dict[str, Any]:
    """Prune low-importance memory entries across all agents.

    Runs via Celery beat every 30 minutes.  Applies importance scoring and
    removes entries below the configured threshold.  Also deduplicates
    near-identical vector embeddings in Qdrant (cosine similarity > 0.95).
    """
    logger.info("memory_pruning_started")
    try:
        from app.core.memory.retrieval import MemoryRetrievalPipeline

        pipeline = MemoryRetrievalPipeline()
        stats = _run(pipeline.prune_low_importance())
        logger.info("memory_pruning_completed", stats=stats)
        return {"success": True, "stats": stats}
    except Exception as exc:
        logger.error("memory_pruning_failed", error=str(exc))
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Periodic heartbeat sweep
# ---------------------------------------------------------------------------


@shared_task(
    name="app.workers.agent_worker.agent_heartbeat_sweep",
    bind=False,
    acks_late=True,
    ignore_result=True,
)
def agent_heartbeat_sweep() -> None:
    """Evaluate all running agents — runs via Celery beat every 60 seconds.

    For each agent in RUNNING / EXECUTING / PLANNING state:
    - Checks if heartbeat timeout has elapsed → marks as PAUSED if stale
    - Emits a heartbeat metric for Prometheus
    - Fires ``agent.heartbeat`` event to the event bus
    """
    logger.debug("agent_heartbeat_sweep_started")
    try:
        from app.core.agent_runtime.heartbeat import HeartbeatMonitor

        monitor = HeartbeatMonitor()
        _run(monitor.sweep_all())
    except Exception as exc:
        logger.error("agent_heartbeat_sweep_failed", error=str(exc))
