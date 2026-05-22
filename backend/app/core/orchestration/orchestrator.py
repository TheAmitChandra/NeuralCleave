"""
orchestrator.py — MultiAgentOrchestrator

Coordinates the full plan → route → execute → validate → critique
pipeline across all orchestration agents.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.orchestration.critic import CriticAgent, PlanCritique
from app.core.orchestration.executor import ExecutionResult, ExecutorAgent
from app.core.orchestration.planner import Plan, PlannerAgent
from app.core.orchestration.router import RouterAgent, RoutingDecision
from app.core.orchestration.validator import ValidationResult, ValidatorAgent


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


@dataclass
class OrchestrationResult:
    """Full output of a single orchestration run."""

    run_id: str
    plan: Plan
    routing_decisions: list[RoutingDecision] = field(default_factory=list)
    execution_results: list[ExecutionResult] = field(default_factory=list)
    validation_results: list[ValidationResult] = field(default_factory=list)
    plan_critique: PlanCritique | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if not self.execution_results:
            return 0.0
        passed = sum(1 for r in self.execution_results if r.success)
        return passed / len(self.execution_results)

    @property
    def all_valid(self) -> bool:
        return bool(self.validation_results) and all(
            v.valid for v in self.validation_results
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan.plan_id,
            "goal": self.plan.goal,
            "success_rate": self.success_rate,
            "all_valid": self.all_valid,
            "routing_decisions": [d.to_dict() for d in self.routing_decisions],
            "execution_results": [r.to_dict() for r in self.execution_results],
            "validation_results": [v.to_dict() for v in self.validation_results],
            "plan_critique": self.plan_critique.to_dict() if self.plan_critique else None,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# MultiAgentOrchestrator
# ---------------------------------------------------------------------------


class MultiAgentOrchestrator:
    """Wires PlannerAgent → RouterAgent → ExecutorAgent → ValidatorAgent → CriticAgent.

    The pipeline runs in topological batch order so independent tasks
    execute in parallel within each batch, then sequential batches
    follow dependency constraints.
    """

    def __init__(
        self,
        orchestrator_id: str | None = None,
        planner: PlannerAgent | None = None,
        router: RouterAgent | None = None,
        executor: ExecutorAgent | None = None,
        validator: ValidatorAgent | None = None,
        critic: CriticAgent | None = None,
        enable_critique: bool = True,
    ) -> None:
        self.orchestrator_id: str = orchestrator_id or str(uuid.uuid4())
        self.planner: PlannerAgent = planner or PlannerAgent()
        self.router: RouterAgent = router or RouterAgent()
        self.executor: ExecutorAgent = executor or ExecutorAgent()
        self.validator: ValidatorAgent = validator or ValidatorAgent()
        self.critic: CriticAgent = critic or CriticAgent()
        self.enable_critique: bool = enable_critique

    # ------------------------------------------------------------------
    # Primary entry-point
    # ------------------------------------------------------------------

    async def run(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        tool_registry: Any = None,
    ) -> OrchestrationResult:
        """Execute the full plan → route → execute → validate → critique pipeline."""
        run_id = str(uuid.uuid4())
        ctx = context or {}

        # 1. Plan
        plan = await self.planner.plan(goal, context=ctx)

        # 2. Route
        routing_decisions = await self.router.route(plan)

        # 3. Execute in topological batch order
        execution_results: list[ExecutionResult] = []
        batches = plan.execution_order()
        for batch in batches:
            batch_results = await self.executor.execute_batch(
                batch, tool_registry=tool_registry, parallel=True
            )
            execution_results.extend(batch_results)

        # 4. Validate
        task_map = {t.task_id: t for t in plan.subtasks}
        result_map = {r.task_id: r for r in execution_results}
        pairs = [
            (task_map[tid], result_map[tid])
            for tid in task_map
            if tid in result_map
        ]
        validation_results = await self.validator.validate_batch(pairs)

        # 5. Critique (optional)
        plan_critique: PlanCritique | None = None
        if self.enable_critique:
            plan_critique = await self.critic.critique_plan(
                plan, execution_results, validation_results
            )

        return OrchestrationResult(
            run_id=run_id,
            plan=plan,
            routing_decisions=routing_decisions,
            execution_results=execution_results,
            validation_results=validation_results,
            plan_critique=plan_critique,
            metadata={"orchestrator_id": self.orchestrator_id, "context": ctx},
        )

    # ------------------------------------------------------------------
    # Run from pre-built plan
    # ------------------------------------------------------------------

    async def run_plan(
        self,
        plan: Plan,
        tool_registry: Any = None,
    ) -> OrchestrationResult:
        """Execute an existing Plan through the route → execute → validate → critique pipeline."""
        run_id = str(uuid.uuid4())

        routing_decisions = await self.router.route(plan)

        execution_results: list[ExecutionResult] = []
        for batch in plan.execution_order():
            batch_results = await self.executor.execute_batch(
                batch, tool_registry=tool_registry, parallel=True
            )
            execution_results.extend(batch_results)

        task_map = {t.task_id: t for t in plan.subtasks}
        result_map = {r.task_id: r for r in execution_results}
        pairs = [
            (task_map[tid], result_map[tid])
            for tid in task_map
            if tid in result_map
        ]
        validation_results = await self.validator.validate_batch(pairs)

        plan_critique: PlanCritique | None = None
        if self.enable_critique:
            plan_critique = await self.critic.critique_plan(
                plan, execution_results, validation_results
            )

        return OrchestrationResult(
            run_id=run_id,
            plan=plan,
            routing_decisions=routing_decisions,
            execution_results=execution_results,
            validation_results=validation_results,
            plan_critique=plan_critique,
            metadata={"orchestrator_id": self.orchestrator_id},
        )
