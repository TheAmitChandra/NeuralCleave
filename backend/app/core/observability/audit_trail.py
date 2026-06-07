"""Audit Trail — tamper-evident log of governance-relevant actions.

Records every authorization decision (allowed / denied / pending) with actor,
action, resource, outcome, and arbitrary metadata.  The ``AuditTrail`` class
is a lightweight in-memory store suitable for integration tests and short-lived
processes; production deployments should flush records to a persistent backend.

Classes:
    AuditOutcome   — string enum for the three possible outcomes
    AuditEvent     — immutable dataclass representing a single audit record
    AuditTrail     — append-only collection with rich query interface

Usage::

    trail = AuditTrail()
    event = trail.record(
        actor_id="user:alice",
        action="deploy",
        resource="service:backend",
        outcome="allowed",
        metadata={"ip": "10.0.0.1"},
    )
    print(event.event_id)       # unique UUID string
    denied = trail.get_events(outcome="denied")
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AuditOutcome(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    PENDING = "pending"


_VALID_OUTCOMES: frozenset[str] = frozenset(o.value for o in AuditOutcome)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditEvent:
    """Immutable record of a single audited action."""

    event_id: str
    actor_id: str
    action: str
    resource: str
    outcome: str  # one of AuditOutcome values
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# AuditTrail
# ---------------------------------------------------------------------------


class AuditTrail:
    """Append-only audit trail with filtering and summary helpers.

    Thread-safe via an internal ``threading.Lock``.

    Args:
        max_events: Maximum events to retain.  When exceeded the oldest event
            is evicted (FIFO).  ``0`` means unlimited.
    """

    def __init__(self, max_events: int = 0) -> None:
        if max_events < 0:
            raise ValueError("max_events must be >= 0 (0 = unlimited)")
        self._max_events = max_events
        self._events: list[AuditEvent] = []
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        actor_id: str,
        action: str,
        resource: str,
        outcome: str,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        """Append a new audit event and return it.

        Args:
            actor_id:  Identity of the principal performing the action.
            action:    Verb describing what was attempted (e.g. "deploy").
            resource:  Target resource identifier (e.g. "service:backend").
            outcome:   One of "allowed", "denied", "pending".
            metadata:  Optional free-form key/value pairs.
            timestamp: Override timestamp (defaults to UTC now).

        Returns:
            The newly created ``AuditEvent``.

        Raises:
            ValueError: If *outcome* is not a recognised value.
        """
        if outcome not in _VALID_OUTCOMES:
            raise ValueError(
                f"Invalid outcome {outcome!r}. Must be one of {sorted(_VALID_OUTCOMES)}"
            )
        if not actor_id:
            raise ValueError("actor_id must not be empty")
        if not action:
            raise ValueError("action must not be empty")
        if not resource:
            raise ValueError("resource must not be empty")

        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            actor_id=actor_id,
            action=action,
            resource=resource,
            outcome=outcome,
            timestamp=timestamp or datetime.now(tz=timezone.utc),
            metadata=dict(metadata) if metadata else {},
        )
        with self._lock:
            if self._max_events and len(self._events) >= self._max_events:
                self._events.pop(0)
            self._events.append(event)
        return event

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_events(
        self,
        actor_id: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        resource: str | None = None,
    ) -> list[AuditEvent]:
        """Return events matching ALL supplied filters (None = any).

        Returns events in insertion order (oldest first).
        """
        with self._lock:
            events = list(self._events)

        if actor_id is not None:
            events = [e for e in events if e.actor_id == actor_id]
        if action is not None:
            events = [e for e in events if e.action == action]
        if outcome is not None:
            events = [e for e in events if e.outcome == outcome]
        if resource is not None:
            events = [e for e in events if e.resource == resource]
        return events

    def get_event(self, event_id: str) -> AuditEvent | None:
        """Return event by ID or ``None`` if not found."""
        with self._lock:
            for e in self._events:
                if e.event_id == event_id:
                    return e
        return None

    # ------------------------------------------------------------------
    # Summary helpers
    # ------------------------------------------------------------------

    @property
    def event_count(self) -> int:
        """Total number of events currently stored."""
        with self._lock:
            return len(self._events)

    def outcome_counts(self) -> dict[str, int]:
        """Return ``{outcome: count}`` for all recorded events."""
        counts: dict[str, int] = {o.value: 0 for o in AuditOutcome}
        with self._lock:
            for e in self._events:
                counts[e.outcome] = counts.get(e.outcome, 0) + 1
        return counts

    def actors(self) -> list[str]:
        """Sorted deduplicated list of actor IDs in the trail."""
        with self._lock:
            return sorted({e.actor_id for e in self._events})

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all events."""
        with self._lock:
            self._events.clear()
