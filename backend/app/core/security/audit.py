"""Audit Logging — structured, tamper-evident audit trail.

Every security-relevant event in CortexFlow must be recorded here:
    - tool executions (success and failure)
    - permission checks (granted and denied)
    - authentication events (login, token refresh, logout)
    - approval decisions (approved / rejected)
    - policy changes
    - sandbox events

Design:
    ``AuditEvent``     — Pydantic model for a single audit record.
    ``AuditLogger``    — async writer that persists to the ``audit_logs`` table
                         via SQLAlchemy and emits a structlog line simultaneously.
    ``log_tool_call()`` / ``log_auth_event()`` / ``log_permission_check()``
                       — typed convenience functions used throughout the codebase.

The ``audit_logs`` table is append-only by convention (no UPDATE / DELETE
operations are issued by this module).  An ``event_hash`` SHA-256 fingerprint
over the core fields provides basic tamper detection.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

class AuditEventType(str, Enum):
    # Tool system
    TOOL_EXECUTED = "tool.executed"
    TOOL_FAILED = "tool.failed"
    TOOL_BLOCKED = "tool.blocked"
    TOOL_APPROVED = "tool.approved"
    TOOL_REJECTED = "tool.rejected"

    # Auth
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESHED = "auth.token_refreshed"
    AUTH_TOKEN_REVOKED = "auth.token_revoked"

    # Permissions
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"

    # Approvals
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_TIMEOUT = "approval.timeout"

    # Security
    INJECTION_DETECTED = "security.injection_detected"
    SANDBOX_ESCAPED = "security.sandbox_escaped"
    RATE_LIMIT_HIT = "security.rate_limit_hit"

    # Policy
    POLICY_CREATED = "policy.created"
    POLICY_UPDATED = "policy.updated"
    POLICY_DELETED = "policy.deleted"

    # Agent lifecycle
    AGENT_CREATED = "agent.created"
    AGENT_TERMINATED = "agent.terminated"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

class AuditEvent(BaseModel):
    """A single audit record.

    Attributes:
        event_id:    Globally unique identifier for this record.
        event_type:  Taxonomy label (see ``AuditEventType``).
        severity:    Severity level.
        actor_id:    UUID of the user/agent that triggered the event.
        actor_type:  ``"user"`` | ``"agent"`` | ``"system"``.
        resource_id: UUID of the affected resource (tool, agent, workflow…).
        resource_type: Type of the resource.
        tenant_id:   Multi-tenancy partition key.
        details:     Free-form JSON payload (tool params, permission scope, etc.)
        ip_address:  Source IP (auth events).
        trace_id:    OpenTelemetry trace ID for correlation.
        occurred_at: UTC timestamp of the event.
        event_hash:  SHA-256 over canonical fields for tamper detection.
    """

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.INFO
    actor_id: uuid.UUID | None = None
    actor_type: str = "system"  # user | agent | system
    resource_id: str | None = None
    resource_type: str | None = None
    tenant_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    trace_id: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_hash: str = ""  # computed on creation

    def model_post_init(self, __context: Any) -> None:
        if not self.event_hash:
            self.event_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """SHA-256 over deterministic canonical fields."""
        canonical = json.dumps(
            {
                "event_id": str(self.event_id),
                "event_type": self.event_type.value,
                "actor_id": str(self.actor_id) if self.actor_id else None,
                "resource_id": self.resource_id,
                "occurred_at": self.occurred_at.isoformat(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def verify_hash(self) -> bool:
        """Return True if the stored hash matches re-computed hash."""
        return self.event_hash == self._compute_hash()


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Async audit writer.

    Writes to:
    1. structlog (JSON log line) — synchronous, always executed.
    2. PostgreSQL ``audit_logs`` table — async, via provided session.

    The database model is imported lazily to avoid circular imports.
    """

    async def write(self, event: AuditEvent, session: AsyncSession | None = None) -> None:
        """Persist an audit event.

        Parameters:
            event:   The ``AuditEvent`` to record.
            session: Optional SQLAlchemy session.  If ``None`` the event is
                     only written to the structured log.
        """
        # Always emit a structured log line
        log_fn = logger.warning if event.severity in (AuditSeverity.WARNING, AuditSeverity.ERROR, AuditSeverity.CRITICAL) else logger.info
        log_fn(
            "audit.event",
            event_id=str(event.event_id),
            event_type=event.event_type.value,
            severity=event.severity.value,
            actor_id=str(event.actor_id) if event.actor_id else None,
            actor_type=event.actor_type,
            resource_id=event.resource_id,
            resource_type=event.resource_type,
            tenant_id=event.tenant_id,
            trace_id=event.trace_id,
            occurred_at=event.occurred_at.isoformat(),
            event_hash=event.event_hash,
        )

        if session is not None:
            await self._write_to_db(event, session)

    async def _write_to_db(self, event: AuditEvent, session: AsyncSession) -> None:
        """Insert an audit record into the database."""
        try:
            from app.db.models.audit import AuditLog  # type: ignore[import]
            row = AuditLog(
                id=event.event_id,
                event_type=event.event_type.value,
                severity=event.severity.value,
                actor_id=event.actor_id,
                actor_type=event.actor_type,
                resource_id=event.resource_id,
                resource_type=event.resource_type,
                tenant_id=event.tenant_id,
                details=event.details,
                ip_address=event.ip_address,
                trace_id=event.trace_id,
                occurred_at=event.occurred_at,
                event_hash=event.event_hash,
            )
            session.add(row)
            await session.flush()
        except Exception as exc:  # noqa: BLE001
            # Audit write failure must NEVER crash the main request
            logger.error(
                "audit.db_write_failed",
                event_id=str(event.event_id),
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_AUDIT_LOGGER = AuditLogger()


# ---------------------------------------------------------------------------
# Typed convenience helpers
# ---------------------------------------------------------------------------

async def log_tool_call(
    *,
    tool_name: str,
    agent_id: uuid.UUID | None,
    success: bool,
    risk_score: float,
    details: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Record a tool execution event."""
    event_type = AuditEventType.TOOL_EXECUTED if success else AuditEventType.TOOL_FAILED
    severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
    if risk_score >= 75:
        severity = AuditSeverity.WARNING if success else AuditSeverity.ERROR

    event = AuditEvent(
        event_type=event_type,
        severity=severity,
        actor_id=agent_id,
        actor_type="agent",
        resource_id=tool_name,
        resource_type="tool",
        tenant_id=tenant_id,
        trace_id=trace_id,
        details={"risk_score": risk_score, **(details or {})},
    )
    await _AUDIT_LOGGER.write(event, session)


async def log_auth_event(
    *,
    event_type: AuditEventType,
    user_id: uuid.UUID | None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
    trace_id: str | None = None,
) -> None:
    """Record an authentication event."""
    severity = AuditSeverity.WARNING if "failed" in event_type.value else AuditSeverity.INFO
    event = AuditEvent(
        event_type=event_type,
        severity=severity,
        actor_id=user_id,
        actor_type="user",
        resource_type="auth",
        ip_address=ip_address,
        trace_id=trace_id,
        details=details or {},
    )
    await _AUDIT_LOGGER.write(event, session)


async def log_permission_check(
    *,
    actor_id: uuid.UUID | None,
    actor_type: str,
    permission: str,
    granted: bool,
    resource_id: str | None = None,
    session: AsyncSession | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Record a permission grant or denial."""
    event = AuditEvent(
        event_type=AuditEventType.PERMISSION_GRANTED if granted else AuditEventType.PERMISSION_DENIED,
        severity=AuditSeverity.INFO if granted else AuditSeverity.WARNING,
        actor_id=actor_id,
        actor_type=actor_type,
        resource_id=resource_id,
        resource_type="permission",
        tenant_id=tenant_id,
        trace_id=trace_id,
        details={"permission": permission, "granted": granted},
    )
    await _AUDIT_LOGGER.write(event, session)


async def log_injection_detected(
    *,
    source: str,
    confidence: float,
    patterns: list[str],
    actor_id: uuid.UUID | None = None,
    session: AsyncSession | None = None,
    trace_id: str | None = None,
) -> None:
    """Record a detected prompt injection attempt."""
    event = AuditEvent(
        event_type=AuditEventType.INJECTION_DETECTED,
        severity=AuditSeverity.CRITICAL,
        actor_id=actor_id,
        actor_type="user" if actor_id else "system",
        resource_type="prompt",
        trace_id=trace_id,
        details={"source": source, "confidence": confidence, "patterns": patterns},
    )
    await _AUDIT_LOGGER.write(event, session)


async def log_approval_event(
    *,
    event_type: AuditEventType,
    approval_id: str,
    actor_id: uuid.UUID | None,
    actor_type: str = "user",
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
    trace_id: str | None = None,
) -> None:
    """Record an approval lifecycle event."""
    event = AuditEvent(
        event_type=event_type,
        severity=AuditSeverity.INFO,
        actor_id=actor_id,
        actor_type=actor_type,
        resource_id=approval_id,
        resource_type="approval",
        trace_id=trace_id,
        details={"resource": resource_id, **(details or {})},
    )
    await _AUDIT_LOGGER.write(event, session)
