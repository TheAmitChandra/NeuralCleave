"""
router.py — RouterAgent

Routes SubTasks in a Plan to appropriate agent types using
keyword matching, payload hints, and explicit assignments.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.orchestration.planner import Plan, SubTask


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """Records which agent type a task was assigned to and why."""

    task_id: str
    assigned_agent_type: str
    priority: int
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "assigned_agent_type": self.assigned_agent_type,
            "priority": self.priority,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RoutingError(Exception):
    """Raised when a task cannot be routed."""


# ---------------------------------------------------------------------------
# RouterAgent
# ---------------------------------------------------------------------------


class RouterAgent:
    """Assigns tasks in a Plan to agent types.

    Routing priority (highest first):
    1. ``subtask.assigned_to`` — explicit assignment
    2. Keyword match in task description against the routing table
    3. ``subtask.payload["agent_type"]`` — payload hint
    4. ``DEFAULT_AGENT_TYPE`` — fallback
    """

    DEFAULT_AGENT_TYPE: str = "generic_executor"

    def __init__(self, agent_id: str | None = None) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        # keyword (lower) → agent_type
        self._routing_table: dict[str, str] = {}
        # agent_type → [capabilities]
        self._workers: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Worker registration
    # ------------------------------------------------------------------

    def register_worker(self, agent_type: str, capabilities: list[str]) -> None:
        """Register an agent type with its capabilities.

        Capabilities are also added as routing keywords automatically.
        """
        if not agent_type or not agent_type.strip():
            raise ValueError("agent_type cannot be empty")
        self._workers[agent_type] = list(capabilities)
        for cap in capabilities:
            self._routing_table.setdefault(cap.lower(), agent_type)

    # ------------------------------------------------------------------
    # Routing table management
    # ------------------------------------------------------------------

    def add_route(self, keyword: str, agent_type: str) -> None:
        """Explicitly map a keyword to an agent type."""
        self._routing_table[keyword.lower()] = agent_type

    def get_routing_table(self) -> dict[str, str]:
        return dict(self._routing_table)

    def get_workers(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._workers.items()}

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _match_agent_type(self, subtask: SubTask) -> tuple[str, str]:
        """Return *(agent_type, reason)* for a single subtask."""
        # 1. Explicit assignment
        if subtask.assigned_to:
            return subtask.assigned_to, "explicitly assigned"

        # 2. Keyword match in description
        desc_lower = subtask.description.lower()
        for keyword, agent_type in self._routing_table.items():
            if keyword in desc_lower:
                return agent_type, f"keyword match: '{keyword}'"

        # 3. Payload hint
        hint = subtask.payload.get("agent_type")
        if hint:
            return hint, "payload hint"

        # 4. Default fallback
        return self.DEFAULT_AGENT_TYPE, "default fallback"

    async def route(self, plan: Plan) -> list[RoutingDecision]:
        """Route every subtask in *plan* and return all decisions."""
        return [
            RoutingDecision(
                task_id=st.task_id,
                assigned_agent_type=agent_type,
                priority=st.priority,
                reason=reason,
            )
            for st in plan.subtasks
            for agent_type, reason in [self._match_agent_type(st)]
        ]

    async def route_single(self, subtask: SubTask) -> RoutingDecision:
        """Route a single subtask."""
        agent_type, reason = self._match_agent_type(subtask)
        return RoutingDecision(
            task_id=subtask.task_id,
            assigned_agent_type=agent_type,
            priority=subtask.priority,
            reason=reason,
        )
