"""CortexFlow Celery application — worker pool configuration and task routing.

Queues
──────
Eight dedicated queues allow independent horizontal scaling of each concern:

  planning_queue      PlannerAgent task decomposition          priority: high
  execution_queue     Tool execution and sandbox ops           priority: high
  validation_queue    ValidatorAgent + CriticAgent checks      priority: medium
  reflection_queue    Reflection engine, quality scoring       priority: medium
  observability_queue Metrics, tracing, audit writes           priority: low
  high_priority_queue Time-critical agent tasks                priority: critical
  low_priority_queue  Background learning and pruning          priority: low
  approval_queue      Human approval gate requests             priority: high

Startup
───────
  celery -A app.workers.celery_app worker \\
      --queues=execution_queue,planning_queue,approval_queue \\
      --concurrency=4 --loglevel=info

Beat scheduler (cron triggers)
───────────────────────────────
  celery -A app.workers.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

celery_app = Celery(
    "cortexflow",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.agent_worker",
        "app.workers.workflow_worker",
    ],
)

# ---------------------------------------------------------------------------
# Queue & Exchange definitions
# ---------------------------------------------------------------------------

_default_exchange = Exchange("cortexflow", type="direct")

celery_app.conf.task_queues = [
    Queue(
        "high_priority_queue",
        _default_exchange,
        routing_key="high_priority",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "planning_queue",
        _default_exchange,
        routing_key="planning",
        queue_arguments={"x-max-priority": 8},
    ),
    Queue(
        "execution_queue",
        _default_exchange,
        routing_key="execution",
        queue_arguments={"x-max-priority": 8},
    ),
    Queue(
        "approval_queue",
        _default_exchange,
        routing_key="approval",
        queue_arguments={"x-max-priority": 8},
    ),
    Queue(
        "validation_queue",
        _default_exchange,
        routing_key="validation",
        queue_arguments={"x-max-priority": 5},
    ),
    Queue(
        "reflection_queue",
        _default_exchange,
        routing_key="reflection",
        queue_arguments={"x-max-priority": 5},
    ),
    Queue(
        "observability_queue",
        _default_exchange,
        routing_key="observability",
        queue_arguments={"x-max-priority": 2},
    ),
    Queue(
        "low_priority_queue",
        _default_exchange,
        routing_key="low_priority",
        queue_arguments={"x-max-priority": 1},
    ),
]

celery_app.conf.task_default_queue = "execution_queue"
celery_app.conf.task_default_exchange = "cortexflow"
celery_app.conf.task_default_routing_key = "execution"

# ---------------------------------------------------------------------------
# Task routing — maps task paths to queues
# ---------------------------------------------------------------------------

celery_app.conf.task_routes = {
    # Agent tasks
    "app.workers.agent_worker.run_agent_task": {"queue": "execution_queue"},
    "app.workers.agent_worker.dispatch_agent_action": {"queue": "high_priority_queue"},
    "app.workers.agent_worker.terminate_agent": {"queue": "high_priority_queue"},
    # Workflow tasks
    "app.workers.workflow_worker.execute_workflow": {"queue": "execution_queue"},
    "app.workers.workflow_worker.execute_workflow_node": {"queue": "execution_queue"},
    "app.workers.workflow_worker.validate_workflow_result": {"queue": "validation_queue"},
    "app.workers.workflow_worker.reflect_on_workflow": {"queue": "reflection_queue"},
    "app.workers.workflow_worker.rollback_workflow": {"queue": "high_priority_queue"},
    "app.workers.workflow_worker.checkpoint_workflow_state": {"queue": "observability_queue"},
    # Planning tasks
    "app.workers.agent_worker.decompose_task": {"queue": "planning_queue"},
    # Validation / Reflection tasks
    "app.workers.agent_worker.validate_agent_output": {"queue": "validation_queue"},
    "app.workers.agent_worker.critique_agent_output": {"queue": "validation_queue"},
    "app.workers.agent_worker.reflect_on_execution": {"queue": "reflection_queue"},
    # Observability / Audit tasks
    "app.workers.agent_worker.write_audit_event": {"queue": "observability_queue"},
    "app.workers.workflow_worker.write_audit_event": {"queue": "observability_queue"},
    # Approval tasks
    "app.workers.agent_worker.request_human_approval": {"queue": "approval_queue"},
    "app.workers.workflow_worker.request_human_approval": {"queue": "approval_queue"},
    # Background learning tasks
    "app.workers.agent_worker.update_behavioral_weights": {"queue": "low_priority_queue"},
    "app.workers.agent_worker.prune_memory": {"queue": "low_priority_queue"},
}

# ---------------------------------------------------------------------------
# Serialization & result settings
# ---------------------------------------------------------------------------

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Results
    result_expires=3600,  # 1 hour
    result_persistent=True,
    # Timeouts
    task_soft_time_limit=300,  # 5 min soft → raises SoftTimeLimitExceeded
    task_time_limit=360,  # 6 min hard → kills worker process
    # Acknowledgement
    task_acks_late=True,  # Acknowledge after completion (safer)
    task_reject_on_worker_lost=True,
    # Prefetch — 1 task at a time for predictable resource use
    worker_prefetch_multiplier=1,
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Concurrency
    worker_max_tasks_per_child=500,  # Recycle worker after N tasks (memory leak guard)
)

# ---------------------------------------------------------------------------
# Beat schedule — periodic / cron tasks
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # Heartbeat: evaluate all running agents every 60 seconds
    "agent-heartbeat": {
        "task": "app.workers.agent_worker.agent_heartbeat_sweep",
        "schedule": 60.0,
        "options": {"queue": "high_priority_queue"},
    },
    # Memory pruning: remove low-importance entries every 30 minutes
    "memory-pruning": {
        "task": "app.workers.agent_worker.prune_memory",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "low_priority_queue"},
    },
    # Observability flush: force-flush any buffered metrics every 15 seconds
    "metrics-flush": {
        "task": "app.workers.agent_worker.write_audit_event",
        "schedule": 15.0,
        "args": [{"event_type": "metrics_flush", "payload": {}}],
        "options": {"queue": "observability_queue"},
    },
    # Workflow stale-check: detect and recover stuck workflows every 5 minutes
    "stale-workflow-recovery": {
        "task": "app.workers.workflow_worker.recover_stale_workflows",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "high_priority_queue"},
    },
    # Behavioral weight update: consolidate learning data nightly at 02:00 UTC
    "nightly-learning-consolidation": {
        "task": "app.workers.agent_worker.update_behavioral_weights",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "low_priority_queue"},
    },
}
