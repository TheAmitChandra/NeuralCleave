"""
planner.py — PlannerAgent

Decomposes a high-level goal into a structured Plan of SubTasks,
respecting topological ordering for dependency-aware execution.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SubTask:
    """A single unit of work within a Plan."""

    task_id: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    assigned_to: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "assigned_to": self.assigned_to,
            "payload": dict(self.payload),
            "priority": self.priority,
        }


@dataclass
class Plan:
    """An ordered collection of SubTasks derived from a goal."""

    plan_id: str
    goal: str
    subtasks: list[SubTask] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_subtask(self, subtask: SubTask) -> None:
        self.subtasks.append(subtask)

    def get_subtask(self, task_id: str) -> SubTask | None:
        return next((t for t in self.subtasks if t.task_id == task_id), None)

    # ------------------------------------------------------------------
    # Topological ordering
    # ------------------------------------------------------------------

    def execution_order(self) -> list[list[SubTask]]:
        """Return subtasks as parallel batches (topological / BFS sort).

        Each inner list contains tasks that can run concurrently.
        Raises ``ValueError`` on circular dependencies.
        """
        if not self.subtasks:
            return []

        task_map: dict[str, SubTask] = {t.task_id: t for t in self.subtasks}
        valid_ids: set[str] = set(task_map.keys())

        # Build in-degree count (only count deps that exist in this plan)
        in_degree: dict[str, int] = {tid: 0 for tid in valid_ids}
        for t in self.subtasks:
            for dep in t.dependencies:
                if dep in valid_ids:
                    in_degree[t.task_id] += 1

        remaining: set[str] = set(valid_ids)
        batches: list[list[SubTask]] = []

        while remaining:
            ready = [tid for tid in remaining if in_degree[tid] == 0]
            if not ready:
                raise ValueError("Circular dependency detected in plan")
            batch = [task_map[tid] for tid in ready]
            batches.append(batch)
            for tid in ready:
                remaining.discard(tid)
                # Decrement dependents
                for t in self.subtasks:
                    if tid in t.dependencies and t.task_id in remaining:
                        in_degree[t.task_id] -= 1

        return batches

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "subtasks": [t.to_dict() for t in self.subtasks],
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PlanDecompositionError(Exception):
    """Raised when a goal cannot be decomposed into a valid Plan."""


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------


class PlannerAgent:
    """Decomposes a natural-language goal into a structured Plan.

    The default ``_decompose`` implementation performs simple
    pattern-based decomposition (numbered / bulleted lists).
    Override ``_decompose`` in subclasses to use an LLM.
    """

    def __init__(
        self,
        agent_id: str | None = None,
        max_subtasks: int = 20,
    ) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.max_subtasks: int = max_subtasks
        self._plans: dict[str, Plan] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def plan(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
    ) -> Plan:
        """Decompose *goal* into a Plan and store it in history."""
        if not goal or not goal.strip():
            raise PlanDecompositionError("Goal cannot be empty")

        ctx = context or {}
        subtasks = self._decompose(goal.strip(), ctx)

        plan = Plan(
            plan_id=str(uuid.uuid4()),
            goal=goal.strip(),
            metadata={"context": ctx, "planner_id": self.agent_id},
        )
        for st in subtasks:
            plan.add_subtask(st)

        self._plans[plan.plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    @property
    def plan_count(self) -> int:
        return len(self._plans)

    # ------------------------------------------------------------------
    # Decomposition (override with LLM in subclasses)
    # ------------------------------------------------------------------

    def _decompose(self, goal: str, context: dict[str, Any]) -> list[SubTask]:
        """Parse goal text into SubTasks.

        Supports:
        - ``1. task one\\n2. task two`` (numbered list)
        - ``- task one\\n- task two``  (bulleted list)
        - Plain text → single SubTask
        """
        lines = [l.strip() for l in goal.splitlines() if l.strip()]

        task_lines: list[str] = []
        for line in lines:
            m = re.match(r"^[\d]+[.)]\s+(.+)$", line) or re.match(r"^[-*]\s+(.+)$", line)
            if m:
                task_lines.append(m.group(1))

        if not task_lines:
            task_lines = [goal]

        if len(task_lines) > self.max_subtasks:
            raise PlanDecompositionError(
                f"Goal decomposes into {len(task_lines)} subtasks, "
                f"exceeding the limit of {self.max_subtasks}"
            )

        sequential: bool = bool(context.get("sequential", False))
        priority: int = int(context.get("priority", 5))

        subtasks: list[SubTask] = []
        for i, desc in enumerate(task_lines):
            deps: list[str] = [subtasks[i - 1].task_id] if sequential and i > 0 else []
            subtasks.append(
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description=desc,
                    dependencies=deps,
                    priority=priority,
                )
            )

        return subtasks
