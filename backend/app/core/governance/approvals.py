"""Human Approval Layer — approval workflow for high-risk agent actions.

Architecture
────────────
An ``ApprovalRequest`` is created whenever an agent wants to execute an
action whose risk score meets or exceeds the configured threshold (default
score ≥ 86, i.e. ``isolation_tier == "blocked"`` in the tool registry).

State machine
─────────────
    PENDING ──► APPROVED ──► EXECUTED
                    └──► EXPIRED
    PENDING ──► REJECTED
    PENDING ──► EXPIRED   (TTL elapsed, no decision)
    PENDING ──► CANCELLED (agent cancelled the request)

Each transition is validated by ``ApprovalWorkflow`` and emitted to the
audit logger. Operator notification hooks (webhook / email) fire on
creation and on decision.

Usage::

    workflow = ApprovalWorkflow(notifier=my_webhook_notifier)

    request = await workflow.request_approval(
        actor_id="agent-001",
        action_description="Delete production database backup",
        risk_score=92,
        tool_name="shell.execute",
        tool_params={"command": "rm -rf /backups/*"},
        requested_by_tenant="tenant-123",
    )

    # Later — operator calls:
    result = await workflow.approve(request.request_id, operator_id="ops-007")
    # or
    result = await workflow.reject(request.request_id, operator_id="ops-007", reason="too dangerous")
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger(__name__)

# Default TTL before an unanswered request expires
_DEFAULT_TTL_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    EXECUTED = "EXECUTED"


class ApprovalPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ApprovalRequest:
    """A single human-approval request.

    Attributes:
        request_id:      Unique ID for this request.
        actor_id:        Agent or user ID that wants to perform the action.
        tool_name:       The tool to be executed upon approval.
        tool_params:     Parameters for the tool call.
        action_description: Human-readable description of the action.
        risk_score:      Numeric risk score (0–100) from the tool registry.
        priority:        Derived from risk_score.
        status:          Current state in the approval state machine.
        tenant_id:       Multi-tenant scope.
        created_at:      UTC timestamp of creation.
        expires_at:      UTC timestamp after which request auto-expires.
        decided_at:      UTC timestamp of the operator decision (if made).
        decided_by:      Operator ID who made the decision.
        rejection_reason: Reason text when status == REJECTED.
        context:         Optional extra metadata for the operator UI.
        request_hash:    SHA-256 of deterministic fields for tamper detection.
    """

    request_id: str
    actor_id: str
    tool_name: str
    tool_params: dict[str, Any]
    action_description: str
    risk_score: int
    priority: ApprovalPriority
    status: ApprovalStatus
    tenant_id: str
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    rejection_reason: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    request_hash: str = ""

    def is_expired(self) -> bool:
        return datetime.now(tz=timezone.utc) >= self.expires_at

    def is_pending(self) -> bool:
        return self.status == ApprovalStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "actor_id": self.actor_id,
            "tool_name": self.tool_name,
            "tool_params": self.tool_params,
            "action_description": self.action_description,
            "risk_score": self.risk_score,
            "priority": self.priority.value,
            "status": self.status.value,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decided_by": self.decided_by,
            "rejection_reason": self.rejection_reason,
            "context": self.context,
            "request_hash": self.request_hash,
        }


@dataclass
class ApprovalDecision:
    """Result returned from approve() / reject() / cancel()."""

    request_id: str
    new_status: ApprovalStatus
    decided_by: str
    decided_at: datetime
    message: str


# ---------------------------------------------------------------------------
# Notifier type alias
# ---------------------------------------------------------------------------

# A notifier is an async callable that receives the ApprovalRequest dict.
# Examples: send to Slack webhook, email, PagerDuty, database, etc.
NotifierFn = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


async def _noop_notifier(payload: dict[str, Any]) -> None:
    """Default notifier — logs the event, no external side effects."""
    logger.info(
        "approval.notification", request_id=payload.get("request_id"), status=payload.get("status")
    )


# ---------------------------------------------------------------------------
# In-memory store (replace with DB-backed store in production)
# ---------------------------------------------------------------------------


class ApprovalStore:
    """Thread-safe in-memory store for ApprovalRequest objects.

    In production this should be replaced with a DB-backed implementation
    that persists to the ``approvals`` PostgreSQL table.
    """

    def __init__(self) -> None:
        self._store: dict[str, ApprovalRequest] = {}
        self._lock = asyncio.Lock()

    async def save(self, request: ApprovalRequest) -> None:
        async with self._lock:
            self._store[request.request_id] = request

    async def get(self, request_id: str) -> ApprovalRequest | None:
        async with self._lock:
            return self._store.get(request_id)

    async def list_pending(self, tenant_id: str | None = None) -> list[ApprovalRequest]:
        async with self._lock:
            results = [
                r
                for r in self._store.values()
                if r.status == ApprovalStatus.PENDING
                and (tenant_id is None or r.tenant_id == tenant_id)
            ]
        return results

    async def list_all(self, tenant_id: str | None = None) -> list[ApprovalRequest]:
        async with self._lock:
            results = [
                r for r in self._store.values() if tenant_id is None or r.tenant_id == tenant_id
            ]
        return results

    async def delete(self, request_id: str) -> None:
        async with self._lock:
            self._store.pop(request_id, None)

    def __len__(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------


class ApprovalWorkflow:
    """Human approval workflow engine.

    Parameters:
        store:                  Storage backend for ApprovalRequest objects.
        notifier:               Async callable notified on create/decide events.
        default_ttl_seconds:    Time before a PENDING request auto-expires.
        risk_threshold_high:    Risk score ≥ this → CRITICAL priority.
        risk_threshold_medium:  Risk score ≥ this → HIGH priority.
    """

    def __init__(
        self,
        store: ApprovalStore | None = None,
        notifier: NotifierFn | None = None,
        default_ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        risk_threshold_high: int = 86,
        risk_threshold_medium: int = 61,
    ) -> None:
        self._store = store if store is not None else ApprovalStore()
        self._notifier = notifier or _noop_notifier
        self._ttl = default_ttl_seconds
        self._threshold_high = risk_threshold_high
        self._threshold_medium = risk_threshold_medium

    # ------------------------------------------------------------------
    # Public API — request
    # ------------------------------------------------------------------

    async def request_approval(
        self,
        *,
        actor_id: str,
        action_description: str,
        risk_score: int,
        tool_name: str,
        tool_params: dict[str, Any],
        tenant_id: str = "default",
        context: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> ApprovalRequest:
        """Create a new approval request and notify operators.

        Returns the created ``ApprovalRequest`` (status=PENDING).
        """
        now = datetime.now(tz=timezone.utc)
        ttl = ttl_seconds or self._ttl
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            actor_id=actor_id,
            tool_name=tool_name,
            tool_params=tool_params,
            action_description=action_description,
            risk_score=risk_score,
            priority=self._derive_priority(risk_score),
            status=ApprovalStatus.PENDING,
            tenant_id=tenant_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            context=context or {},
        )
        request.request_hash = self._compute_hash(request)

        await self._store.save(request)
        logger.info(
            "approval.requested",
            request_id=request.request_id,
            actor_id=actor_id,
            tool_name=tool_name,
            risk_score=risk_score,
            priority=request.priority.value,
        )

        await self._notify(request)
        return request

    # ------------------------------------------------------------------
    # Public API — decisions
    # ------------------------------------------------------------------

    async def approve(
        self,
        request_id: str,
        *,
        operator_id: str,
    ) -> ApprovalDecision:
        """Approve a pending request."""
        await self._load_pending(request_id)
        return await self._decide(
            request_id,
            new_status=ApprovalStatus.APPROVED,
            operator_id=operator_id,
            message=f"Approved by {operator_id}",
        )

    async def reject(
        self,
        request_id: str,
        *,
        operator_id: str,
        reason: str = "",
    ) -> ApprovalDecision:
        """Reject a pending request."""
        request = await self._load_pending(request_id)
        decision = await self._decide(
            request_id,
            new_status=ApprovalStatus.REJECTED,
            operator_id=operator_id,
            message=f"Rejected by {operator_id}: {reason}",
            rejection_reason=reason,
        )
        return decision

    async def cancel(
        self,
        request_id: str,
        *,
        actor_id: str,
    ) -> ApprovalDecision:
        """Cancel a pending request (by the originating actor)."""
        request = await self._load_pending(request_id)
        if request.actor_id != actor_id:
            raise PermissionError(
                f"Actor {actor_id!r} cannot cancel request owned by {request.actor_id!r}"
            )
        return await self._decide(
            request_id,
            new_status=ApprovalStatus.CANCELLED,
            operator_id=actor_id,
            message=f"Cancelled by actor {actor_id}",
        )

    async def mark_executed(self, request_id: str, *, operator_id: str) -> ApprovalDecision:
        """Mark an APPROVED request as EXECUTED after the action runs."""
        request = await self._store.get(request_id)
        if request is None:
            raise KeyError(f"ApprovalRequest {request_id!r} not found")
        if request.status != ApprovalStatus.APPROVED:
            raise ValueError(f"Cannot mark as EXECUTED from status {request.status.value!r}")
        return await self._decide(
            request_id,
            new_status=ApprovalStatus.EXECUTED,
            operator_id=operator_id,
            message="Execution confirmed",
        )

    async def expire_stale(self) -> list[str]:
        """Scan for PENDING requests past their TTL and expire them.

        Returns list of expired request_ids. Intended to be called by a
        background scheduler (e.g. Celery beat task every 5 minutes).
        """
        pending = await self._store.list_pending()
        expired_ids: list[str] = []
        for req in pending:
            if req.is_expired():
                await self._decide(
                    req.request_id,
                    new_status=ApprovalStatus.EXPIRED,
                    operator_id="system",
                    message="TTL elapsed — auto-expired by system",
                )
                expired_ids.append(req.request_id)
        if expired_ids:
            logger.warning("approval.expired_batch", count=len(expired_ids))
        return expired_ids

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def get(self, request_id: str) -> ApprovalRequest | None:
        return await self._store.get(request_id)

    async def list_pending(self, tenant_id: str | None = None) -> list[ApprovalRequest]:
        return await self._store.list_pending(tenant_id)

    async def list_all(self, tenant_id: str | None = None) -> list[ApprovalRequest]:
        return await self._store.list_all(tenant_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_pending(self, request_id: str) -> ApprovalRequest:
        request = await self._store.get(request_id)
        if request is None:
            raise KeyError(f"ApprovalRequest {request_id!r} not found")
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Request {request_id!r} is not PENDING (current: {request.status.value})"
            )
        if request.is_expired():
            # Auto-expire before caller can act on it
            await self._decide(
                request_id,
                new_status=ApprovalStatus.EXPIRED,
                operator_id="system",
                message="TTL elapsed — auto-expired",
            )
            raise ValueError(f"Request {request_id!r} has expired")
        return request

    async def _decide(
        self,
        request_id: str,
        *,
        new_status: ApprovalStatus,
        operator_id: str,
        message: str,
        rejection_reason: str = "",
    ) -> ApprovalDecision:
        request = await self._store.get(request_id)
        if request is None:
            raise KeyError(f"ApprovalRequest {request_id!r} not found")

        now = datetime.now(tz=timezone.utc)
        request.status = new_status
        request.decided_at = now
        request.decided_by = operator_id
        if rejection_reason:
            request.rejection_reason = rejection_reason

        await self._store.save(request)

        logger.info(
            "approval.decision",
            request_id=request_id,
            new_status=new_status.value,
            operator_id=operator_id,
        )
        await self._notify(request)

        return ApprovalDecision(
            request_id=request_id,
            new_status=new_status,
            decided_by=operator_id,
            decided_at=now,
            message=message,
        )

    def _derive_priority(self, risk_score: int) -> ApprovalPriority:
        if risk_score >= self._threshold_high:
            return ApprovalPriority.CRITICAL
        if risk_score >= self._threshold_medium:
            return ApprovalPriority.HIGH
        if risk_score >= 26:
            return ApprovalPriority.MEDIUM
        return ApprovalPriority.LOW

    @staticmethod
    def _compute_hash(request: ApprovalRequest) -> str:
        payload = (
            f"{request.request_id}:{request.actor_id}:{request.tool_name}:"
            f"{request.risk_score}:{request.created_at.isoformat()}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def _notify(self, request: ApprovalRequest) -> None:
        try:
            await self._notifier(request.to_dict())
        except Exception:
            logger.exception("approval.notify_failed", request_id=request.request_id)
