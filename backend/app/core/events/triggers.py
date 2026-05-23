"""
Event Triggers — sources that feed events into the CortexFlow event bus.

Supported trigger types:
  webhook     — inbound HTTP POST from external systems
  cron        — time-based scheduled events (Celery beat)
  database    — PostgreSQL LISTEN/NOTIFY change feed
  monitoring  — Prometheus alertmanager webhook payloads
  github      — GitHub webhook events (push, PR, release, …)
  email       — Email arrival notifications (IMAP / Gmail API)
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums / constants
# ---------------------------------------------------------------------------

class TriggerType(str, Enum):
    WEBHOOK = "webhook"
    CRON = "cron"
    DATABASE = "database"
    MONITORING = "monitoring"
    GITHUB = "github"
    EMAIL = "email"


class TriggerStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Core data classes
# ---------------------------------------------------------------------------

@dataclass
class TriggerEvent:
    """
    A normalised event produced by any trigger source.

    All trigger implementations convert their raw source payload into a
    ``TriggerEvent`` before pushing it onto the event bus.
    """

    trigger_id: str
    trigger_type: TriggerType
    source: str                          # human-readable origin label
    topic: str                           # event bus topic to publish on
    payload: dict[str, Any]
    status: TriggerStatus = TriggerStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "trigger_type": self.trigger_type.value,
            "source": self.source,
            "topic": self.topic,
            "payload": self.payload,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Trigger registry
# ---------------------------------------------------------------------------

class TriggerRegistry:
    """
    Maintains a catalogue of active trigger configurations.

    Each entry maps a *trigger_id* to its configuration dict, enabling
    the caller to list, enable, or disable individual triggers at runtime.
    """

    def __init__(self) -> None:
        self._triggers: dict[str, dict[str, Any]] = {}

    # --- CRUD ---------------------------------------------------------------

    def register(
        self,
        name: str,
        trigger_type: TriggerType,
        config: dict[str, Any] | None = None,
    ) -> str:
        """Register a new trigger and return its generated trigger_id."""
        trigger_id = str(uuid.uuid4())
        self._triggers[trigger_id] = {
            "trigger_id": trigger_id,
            "name": name,
            "trigger_type": trigger_type.value,
            "config": config or {},
            "enabled": True,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        return trigger_id

    def deregister(self, trigger_id: str) -> bool:
        """Remove a trigger. Returns True if it existed."""
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]
            return True
        return False

    def enable(self, trigger_id: str) -> bool:
        if trigger_id in self._triggers:
            self._triggers[trigger_id]["enabled"] = True
            return True
        return False

    def disable(self, trigger_id: str) -> bool:
        if trigger_id in self._triggers:
            self._triggers[trigger_id]["enabled"] = False
            return True
        return False

    def is_enabled(self, trigger_id: str) -> bool:
        entry = self._triggers.get(trigger_id)
        return bool(entry and entry.get("enabled", False))

    def get(self, trigger_id: str) -> dict[str, Any] | None:
        return self._triggers.get(trigger_id)

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._triggers.values())

    def list_by_type(self, trigger_type: TriggerType) -> list[dict[str, Any]]:
        return [t for t in self._triggers.values() if t["trigger_type"] == trigger_type.value]

    def count(self) -> int:
        return len(self._triggers)


# ---------------------------------------------------------------------------
# WebhookTrigger
# ---------------------------------------------------------------------------

class WebhookTrigger:
    """
    Converts inbound HTTP webhook payloads into ``TriggerEvent`` objects.

    Optionally verifies an HMAC-SHA256 signature header to authenticate
    the sender (GitHub-style: ``X-Hub-Signature-256: sha256=<hex>``).
    """

    def __init__(self, source: str = "webhook", secret: str | None = None) -> None:
        self.source = source
        self._secret = secret.encode() if secret else None

    # --- HMAC verification --------------------------------------------------

    def verify_signature(self, body: bytes, signature_header: str) -> bool:
        """
        Return True when the HMAC-SHA256 of *body* matches *signature_header*.

        Expected header format: ``sha256=<hex_digest>``
        """
        if self._secret is None:
            return True  # no secret configured → accept all

        if not signature_header.startswith("sha256="):
            return False

        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        provided = signature_header[len("sha256="):]
        return hmac.compare_digest(expected, provided)

    # --- Event construction -------------------------------------------------

    def build_event(
        self,
        payload: dict[str, Any],
        topic: str = "webhook.received",
        metadata: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        """Wrap a raw webhook payload in a normalised ``TriggerEvent``."""
        return TriggerEvent(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.WEBHOOK,
            source=self.source,
            topic=topic,
            payload=payload,
            metadata=metadata or {},
        )


# ---------------------------------------------------------------------------
# CronTrigger
# ---------------------------------------------------------------------------

# Minimal cron-expression pattern: five fields separated by spaces
_CRON_PATTERN = re.compile(
    r"^(\*|[0-9,\-*/]+)\s+"  # minute
    r"(\*|[0-9,\-*/]+)\s+"  # hour
    r"(\*|[0-9,\-*/]+)\s+"  # day-of-month
    r"(\*|[0-9,\-*/]+)\s+"  # month
    r"(\*|[0-9,\-*/]+)$",  # day-of-week
)


class CronTrigger:
    """
    Represents a scheduled (cron-style) trigger.

    In production, the actual scheduling is performed by **Celery Beat**;
    this class provides the data model and validation logic used to register
    cron triggers and build their ``TriggerEvent`` payloads.
    """

    def __init__(self, name: str, cron_expression: str, task_name: str | None = None) -> None:
        if not _CRON_PATTERN.match(cron_expression.strip()):
            raise ValueError(f"Invalid cron expression: {cron_expression!r}")
        self.name = name
        self.cron_expression = cron_expression.strip()
        self.task_name = task_name or name

    def build_event(self, metadata: dict[str, Any] | None = None) -> TriggerEvent:
        """Build the ``TriggerEvent`` emitted when this cron fires."""
        return TriggerEvent(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.CRON,
            source="cron_scheduler",
            topic=f"cron.{self.name}",
            payload={"task_name": self.task_name, "cron": self.cron_expression},
            metadata=metadata or {},
        )

    def to_celery_schedule(self) -> dict[str, Any]:
        """Return a dict compatible with Celery Beat's ``beat_schedule`` entry."""
        fields = self.cron_expression.split()
        return {
            "task": self.task_name,
            "schedule": {
                "minute": fields[0],
                "hour": fields[1],
                "day_of_month": fields[2],
                "month_of_year": fields[3],
                "day_of_week": fields[4],
            },
        }


# ---------------------------------------------------------------------------
# DatabaseTrigger
# ---------------------------------------------------------------------------

class DatabaseTrigger:
    """
    Represents a database change trigger using PostgreSQL LISTEN/NOTIFY.

    Subscribes to a notification channel and converts arriving payloads
    into ``TriggerEvent`` objects.  The actual ``asyncpg.Connection.add_listener``
    call happens in the infrastructure layer; this class owns the data model
    and event construction.
    """

    def __init__(self, channel: str, source: str = "database") -> None:
        if not channel or not channel.replace("_", "").isalnum():
            raise ValueError(f"Invalid PostgreSQL channel name: {channel!r}")
        self.channel = channel
        self.source = source

    def build_event(
        self, raw_payload: str, metadata: dict[str, Any] | None = None
    ) -> TriggerEvent:
        """Build a ``TriggerEvent`` from a raw PostgreSQL NOTIFY payload string."""
        return TriggerEvent(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.DATABASE,
            source=self.source,
            topic=f"db.{self.channel}",
            payload={"channel": self.channel, "raw": raw_payload},
            metadata=metadata or {},
        )


# ---------------------------------------------------------------------------
# MonitoringTrigger
# ---------------------------------------------------------------------------

class MonitoringTrigger:
    """
    Handles inbound Prometheus Alertmanager webhook payloads.

    Alertmanager sends JSON payloads to a configured receiver endpoint.
    This trigger normalises the payload and builds a ``TriggerEvent``
    categorised by alert severity.
    """

    SEVERITY_TOPICS: dict[str, str] = {
        "critical": "monitoring.alert.critical",
        "warning": "monitoring.alert.warning",
        "info": "monitoring.alert.info",
    }
    DEFAULT_TOPIC = "monitoring.alert.unknown"

    def build_event(
        self, payload: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> TriggerEvent:
        """
        Build a ``TriggerEvent`` from an Alertmanager webhook payload.

        The ``payload`` is expected to contain at minimum::

            {"alerts": [{"labels": {"alertname": "...", "severity": "..."}, ...}]}
        """
        alerts = payload.get("alerts", [])
        severity = "unknown"
        if alerts:
            severity = alerts[0].get("labels", {}).get("severity", "unknown").lower()

        topic = self.SEVERITY_TOPICS.get(severity, self.DEFAULT_TOPIC)
        return TriggerEvent(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.MONITORING,
            source="prometheus_alertmanager",
            topic=topic,
            payload=payload,
            metadata={"severity": severity, **(metadata or {})},
        )


# ---------------------------------------------------------------------------
# GitHubTrigger
# ---------------------------------------------------------------------------

class GitHubTrigger:
    """
    Converts GitHub webhook payloads into ``TriggerEvent`` objects.

    Supports optional HMAC-SHA256 signature verification using the webhook
    secret configured in the GitHub repository settings.

    Supported events (non-exhaustive):
      push, pull_request, issues, release, workflow_run, create, delete
    """

    KNOWN_EVENTS = frozenset(
        {
            "push",
            "pull_request",
            "issues",
            "release",
            "workflow_run",
            "create",
            "delete",
            "ping",
        }
    )

    def __init__(self, secret: str | None = None) -> None:
        self._webhook = WebhookTrigger(source="github", secret=secret)

    def verify_signature(self, body: bytes, signature_header: str) -> bool:
        return self._webhook.verify_signature(body, signature_header)

    def build_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        """Build a ``TriggerEvent`` for a GitHub webhook event."""
        safe_type = event_type.lower().replace("-", "_")
        topic = f"github.{safe_type}" if safe_type in self.KNOWN_EVENTS else "github.unknown"
        return TriggerEvent(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.GITHUB,
            source="github_webhook",
            topic=topic,
            payload=payload,
            metadata={"github_event": event_type, **(metadata or {})},
        )


# ---------------------------------------------------------------------------
# EmailTrigger
# ---------------------------------------------------------------------------

class EmailTrigger:
    """
    Represents an email-arrival trigger (IMAP / Gmail API).

    In production the IMAP listener runs in a background Celery task; this
    class owns the data model and event construction logic.
    """

    def __init__(self, mailbox: str = "inbox") -> None:
        self.mailbox = mailbox

    def build_event(
        self,
        sender: str,
        subject: str,
        body_preview: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        """Build a ``TriggerEvent`` representing a new email arrival."""
        return TriggerEvent(
            trigger_id=str(uuid.uuid4()),
            trigger_type=TriggerType.EMAIL,
            source=f"email.{self.mailbox}",
            topic="email.received",
            payload={
                "sender": sender,
                "subject": subject,
                "body_preview": body_preview[:500],
                "mailbox": self.mailbox,
            },
            metadata=metadata or {},
        )
