"""
ObserverAgent — monitors and snapshots the state of agents in an orchestration run.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .orchestrator import OrchestrationResult

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AgentSnapshot:
    """Snapshot of a single agent's state at a point in time."""

    agent_id: str
    status: str  # "idle" | "active" | "error" | "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class SystemSnapshot:
    """Aggregate snapshot of the whole multi-agent system."""

    snapshot_id: str
    timestamp: datetime
    agents: list[AgentSnapshot] = field(default_factory=list)

    @property
    def active_count(self) -> int:
        return sum(1 for a in self.agents if a.status == "active")

    @property
    def healthy_count(self) -> int:
        return sum(1 for a in self.agents if a.status in ("idle", "active"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "agents": [a.to_dict() for a in self.agents],
            "active_count": self.active_count,
            "healthy_count": self.healthy_count,
        }


# ---------------------------------------------------------------------------
# Observer agent
# ---------------------------------------------------------------------------


class ObserverAgent:
    """Observes orchestration runs and maintains per-agent state snapshots."""

    def __init__(self, agent_id: str | None = None) -> None:
        self.agent_id = agent_id or f"observer-{uuid.uuid4().hex[:8]}"
        # registry: agent_id -> {"status": str, "metadata": dict}
        self._registry: dict[str, dict[str, Any]] = {}
        self._last_snapshot: SystemSnapshot | None = None

    # ------------------------------------------------------------------
    # Registry management
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, metadata: dict[str, Any] | None = None) -> None:
        """Register a new agent (status defaults to 'idle')."""
        if agent_id in self._registry:
            raise ValueError(f"Agent '{agent_id}' is already registered")
        self._registry[agent_id] = {
            "status": "idle",
            "metadata": metadata or {},
        }

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        if agent_id not in self._registry:
            raise KeyError(f"Agent '{agent_id}' is not registered")
        del self._registry[agent_id]

    def update_agent_status(
        self,
        agent_id: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update an agent's status (and optionally merge extra metadata)."""
        valid = {"idle", "active", "error", "unknown"}
        if status not in valid:
            raise ValueError(f"Invalid status '{status}'. Must be one of {valid}")
        if agent_id not in self._registry:
            raise KeyError(f"Agent '{agent_id}' is not registered")
        self._registry[agent_id]["status"] = status
        if metadata:
            self._registry[agent_id]["metadata"].update(metadata)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_count(self) -> int:
        return len(self._registry)

    @property
    def active_agents(self) -> list[str]:
        return [aid for aid, info in self._registry.items() if info["status"] == "active"]

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    async def observe(self, orchestration_result: OrchestrationResult) -> SystemSnapshot:
        """
        Build a SystemSnapshot by reading the orchestration result and updating
        internal agent statuses to reflect what just happened.
        """
        now = datetime.now(timezone.utc)

        # Mark agents referenced in routing decisions as active/idle
        for decision in orchestration_result.routing_decisions:
            aid = decision.assigned_agent_type
            if aid in self._registry:
                # If execution succeeded mark idle, otherwise mark error
                exec_res = next(
                    (
                        r
                        for r in orchestration_result.execution_results
                        if r.task_id == decision.task_id
                    ),
                    None,
                )
                new_status = "idle" if (exec_res and exec_res.success) else "error"
                self._registry[aid]["status"] = new_status

        snapshot = self._build_snapshot(now)
        self._last_snapshot = snapshot
        return snapshot

    def get_snapshot(self) -> SystemSnapshot:
        """Return the latest snapshot (builds a fresh one from the registry)."""
        return self._build_snapshot(datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_snapshot(self, ts: datetime) -> SystemSnapshot:
        agents = [
            AgentSnapshot(
                agent_id=aid,
                status=info["status"],
                timestamp=ts,
                metadata=dict(info["metadata"]),
            )
            for aid, info in self._registry.items()
        ]
        return SystemSnapshot(
            snapshot_id=uuid.uuid4().hex,
            timestamp=ts,
            agents=agents,
        )
