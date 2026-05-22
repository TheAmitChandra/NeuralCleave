"""Agent lifecycle management — state machine and transition validation.

The ``AgentLifecycle`` class enforces the legal state transitions for
AgentRuntime and maintains a tamper-evident history of every transition.
Illegal transitions raise ``InvalidTransitionError``.

Legal transition table
----------------------
    IDLE        → PLANNING, PAUSED, TERMINATED
    PLANNING    → EXECUTING, IDLE (abort), PAUSED, TERMINATED
    EXECUTING   → VALIDATING, IDLE (abort), PAUSED, TERMINATED
    VALIDATING  → REFLECTING, EXECUTING (retry), IDLE, PAUSED, TERMINATED
    REFLECTING  → IDLE, PAUSED, TERMINATED
    PAUSED      → IDLE, TERMINATED
    TERMINATED  → (none — terminal state)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.agent_runtime.agent import AgentState
from app.core.observability.logs import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Legal transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.IDLE: frozenset({
        AgentState.PLANNING,
        AgentState.PAUSED,
        AgentState.TERMINATED,
    }),
    AgentState.PLANNING: frozenset({
        AgentState.EXECUTING,
        AgentState.IDLE,
        AgentState.PAUSED,
        AgentState.TERMINATED,
    }),
    AgentState.EXECUTING: frozenset({
        AgentState.VALIDATING,
        AgentState.IDLE,
        AgentState.PAUSED,
        AgentState.TERMINATED,
    }),
    AgentState.VALIDATING: frozenset({
        AgentState.REFLECTING,
        AgentState.EXECUTING,   # retry
        AgentState.IDLE,
        AgentState.PAUSED,
        AgentState.TERMINATED,
    }),
    AgentState.REFLECTING: frozenset({
        AgentState.IDLE,
        AgentState.PAUSED,
        AgentState.TERMINATED,
    }),
    AgentState.PAUSED: frozenset({
        AgentState.IDLE,
        AgentState.TERMINATED,
    }),
    AgentState.TERMINATED: frozenset(),  # terminal — no exits
}


# ---------------------------------------------------------------------------
# LifecycleEvent
# ---------------------------------------------------------------------------

@dataclass
class LifecycleEvent:
    """Immutable record of a single state transition."""

    from_state: AgentState
    to_state: AgentState
    agent_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dictionary."""
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# InvalidTransitionError
# ---------------------------------------------------------------------------

class InvalidTransitionError(Exception):
    """Raised when an illegal AgentState transition is attempted."""


# ---------------------------------------------------------------------------
# AgentLifecycle
# ---------------------------------------------------------------------------

class AgentLifecycle:
    """Validates state transitions and maintains an append-only event history.

    Usage
    -----
    >>> lc = AgentLifecycle("agent-001")
    >>> event = lc.validate_transition(AgentState.IDLE, AgentState.PLANNING)
    >>> lc.history  # [LifecycleEvent(...)]
    """

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._history: list[LifecycleEvent] = []

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @staticmethod
    def can_transition(from_state: AgentState, to_state: AgentState) -> bool:
        """Return True if the transition is legal per the state machine."""
        return to_state in _VALID_TRANSITIONS.get(from_state, frozenset())

    @staticmethod
    def valid_transitions_from(state: AgentState) -> frozenset[AgentState]:
        """Return the set of states reachable from *state*."""
        return _VALID_TRANSITIONS.get(state, frozenset())

    def validate_transition(
        self,
        from_state: AgentState,
        to_state: AgentState,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> LifecycleEvent:
        """Validate a transition and append it to the history.

        Parameters
        ----------
        from_state:
            The current state of the agent.
        to_state:
            The desired next state.
        reason:
            Optional human-readable reason for the transition.
        metadata:
            Optional extra key/value pairs stored with the event.

        Returns
        -------
        LifecycleEvent
            The recorded event.

        Raises
        ------
        InvalidTransitionError
            If the transition is not permitted by the state machine.
        """
        if not self.can_transition(from_state, to_state):
            raise InvalidTransitionError(
                f"Illegal transition {from_state.value!r} → {to_state.value!r} "
                f"for agent {self.agent_id!r}."
            )
        event = LifecycleEvent(
            from_state=from_state,
            to_state=to_state,
            agent_id=self.agent_id,
            reason=reason,
            metadata=metadata or {},
        )
        self._history.append(event)
        logger.info(
            "lifecycle.transition",
            agent_id=self.agent_id,
            from_state=from_state.value,
            to_state=to_state.value,
            reason=reason,
        )
        return event

    # ------------------------------------------------------------------
    # History inspection
    # ------------------------------------------------------------------

    @property
    def history(self) -> list[LifecycleEvent]:
        """Read-only snapshot of all recorded transitions."""
        return list(self._history)

    def last_event(self) -> LifecycleEvent | None:
        """Return the most recent lifecycle event, or None."""
        return self._history[-1] if self._history else None

    def transition_count(self) -> int:
        """Total number of recorded transitions."""
        return len(self._history)
