"""
test_orchestration.py — Integration tests for MultiAgentOrchestrator

Exercises the full plan → route → execute → validate → critique pipeline.
"""
from __future__ import annotations

import pytest

from app.core.orchestration.executor import ExecutionResult, ExecutorAgent
from app.core.orchestration.orchestrator import MultiAgentOrchestrator, OrchestrationResult
from app.core.orchestration.planner import Plan, PlannerAgent, SubTask
from app.core.orchestration.router import RouterAgent
from app.core.orchestration.validator import ValidatorAgent
from app.core.orchestration.critic import CriticAgent


# ---------------------------------------------------------------------------
# TestOrchestrationResult
# ---------------------------------------------------------------------------


class TestOrchestrationResult:
    def _make_result(
        self,
        plan: Plan | None = None,
        exec_results: list | None = None,
        val_results: list | None = None,
    ) -> OrchestrationResult:
        if plan is None:
            plan = Plan(plan_id="p1", goal="test goal")
        return OrchestrationResult(
            run_id="r1",
            plan=plan,
            execution_results=exec_results or [],
            validation_results=val_results or [],
        )

    def test_to_dict_keys(self):
        r = self._make_result()
        d = r.to_dict()
        assert set(d.keys()) == {
            "run_id", "plan_id", "goal", "success_rate", "all_valid",
            "routing_decisions", "execution_results", "validation_results",
            "plan_critique", "metadata",
        }

    def test_success_rate_empty(self):
        r = self._make_result()
        assert r.success_rate == 0.0

    def test_success_rate_all_pass(self):
        plan = Plan(plan_id="p1", goal="g")
        exec_results = [
            ExecutionResult(task_id=f"t{i}", success=True) for i in range(4)
        ]
        r = self._make_result(plan=plan, exec_results=exec_results)
        assert r.success_rate == 1.0

    def test_success_rate_partial(self):
        plan = Plan(plan_id="p1", goal="g")
        exec_results = [
            ExecutionResult(task_id="t0", success=True),
            ExecutionResult(task_id="t1", success=False),
        ]
        r = self._make_result(plan=plan, exec_results=exec_results)
        assert r.success_rate == 0.5

    def test_all_valid_true(self):
        from app.core.orchestration.validator import ValidationResult
        val_results = [
            ValidationResult(task_id="t0", valid=True, confidence=1.0),
            ValidationResult(task_id="t1", valid=True, confidence=1.0),
        ]
        r = self._make_result(val_results=val_results)
        assert r.all_valid is True

    def test_all_valid_false(self):
        from app.core.orchestration.validator import ValidationResult
        val_results = [
            ValidationResult(task_id="t0", valid=True, confidence=1.0),
            ValidationResult(task_id="t1", valid=False, confidence=0.0),
        ]
        r = self._make_result(val_results=val_results)
        assert r.all_valid is False

    def test_all_valid_empty(self):
        r = self._make_result()
        assert r.all_valid is False

    def test_plan_critique_none_by_default(self):
        r = self._make_result()
        assert r.plan_critique is None


# ---------------------------------------------------------------------------
# TestMultiAgentOrchestratorInit
# ---------------------------------------------------------------------------


class TestMultiAgentOrchestratorInit:
    def test_default_id_assigned(self):
        orch = MultiAgentOrchestrator()
        assert orch.orchestrator_id
        assert len(orch.orchestrator_id) == 36

    def test_custom_id(self):
        orch = MultiAgentOrchestrator(orchestrator_id="orch-1")
        assert orch.orchestrator_id == "orch-1"

    def test_default_agents_created(self):
        orch = MultiAgentOrchestrator()
        assert isinstance(orch.planner, PlannerAgent)
        assert isinstance(orch.router, RouterAgent)
        assert isinstance(orch.executor, ExecutorAgent)
        assert isinstance(orch.validator, ValidatorAgent)
        assert isinstance(orch.critic, CriticAgent)

    def test_custom_agents_injected(self):
        planner = PlannerAgent(agent_id="custom-planner")
        orch = MultiAgentOrchestrator(planner=planner)
        assert orch.planner.agent_id == "custom-planner"

    def test_critique_enabled_by_default(self):
        orch = MultiAgentOrchestrator()
        assert orch.enable_critique is True

    def test_critique_disabled(self):
        orch = MultiAgentOrchestrator(enable_critique=False)
        assert orch.enable_critique is False


# ---------------------------------------------------------------------------
# TestMultiAgentOrchestratorRun
# ---------------------------------------------------------------------------


class TestMultiAgentOrchestratorRun:
    async def test_run_simple_goal(self):
        orch = MultiAgentOrchestrator()
        result = await orch.run("do something")
        assert isinstance(result, OrchestrationResult)
        assert result.plan.goal == "do something"
        assert len(result.execution_results) == 1
        assert len(result.validation_results) == 1

    async def test_run_returns_unique_run_id(self):
        orch = MultiAgentOrchestrator()
        r1 = await orch.run("task A")
        r2 = await orch.run("task B")
        assert r1.run_id != r2.run_id

    async def test_run_multi_task_goal(self):
        orch = MultiAgentOrchestrator()
        goal = "1. fetch data\n2. process data\n3. store results"
        result = await orch.run(goal)
        assert len(result.execution_results) == 3
        assert len(result.routing_decisions) == 3

    async def test_run_with_critique_enabled(self):
        orch = MultiAgentOrchestrator(enable_critique=True)
        result = await orch.run("do X")
        assert result.plan_critique is not None
        assert result.plan_critique.plan_id == result.plan.plan_id

    async def test_run_with_critique_disabled(self):
        orch = MultiAgentOrchestrator(enable_critique=False)
        result = await orch.run("do X")
        assert result.plan_critique is None

    async def test_run_all_tasks_succeed_by_default(self):
        orch = MultiAgentOrchestrator()
        result = await orch.run("simple task")
        assert result.success_rate == 1.0

    async def test_run_context_stored_in_metadata(self):
        orch = MultiAgentOrchestrator()
        result = await orch.run("task", context={"env": "test"})
        assert result.metadata["context"]["env"] == "test"

    async def test_run_plan_pipeline(self):
        orch = MultiAgentOrchestrator()
        planner = PlannerAgent()
        plan = await planner.plan("- step one\n- step two")
        result = await orch.run_plan(plan)
        assert len(result.execution_results) == 2
        assert result.success_rate == 1.0

    async def test_run_custom_handler_called(self):
        called: list[str] = []

        async def my_handler(task, registry):
            called.append(task.task_id)
            return "custom output"

        executor = ExecutorAgent()
        executor.register_handler("my_type", my_handler)
        orch = MultiAgentOrchestrator(executor=executor)

        planner = PlannerAgent()
        plan = await planner.plan("run it")
        plan.subtasks[0].payload["task_type"] = "my_type"

        result = await orch.run_plan(plan)
        assert called == [plan.subtasks[0].task_id]
        assert result.execution_results[0].output == "custom output"

    async def test_run_routing_uses_router_config(self):
        router = RouterAgent()
        router.add_route("search", "search_agent")
        orch = MultiAgentOrchestrator(router=router)

        result = await orch.run("search the internet")
        assert result.routing_decisions[0].assigned_agent_type == "search_agent"

    async def test_run_result_to_dict_complete(self):
        orch = MultiAgentOrchestrator()
        result = await orch.run("do a thing")
        d = result.to_dict()
        assert d["run_id"]
        assert d["plan_id"]
        assert isinstance(d["execution_results"], list)
        assert isinstance(d["validation_results"], list)

    async def test_run_sequential_plan_executes_in_order(self):
        orch = MultiAgentOrchestrator()
        result = await orch.run(
            "- step A\n- step B\n- step C",
            context={"sequential": True},
        )
        assert len(result.execution_results) == 3
        # All 3 should succeed
        assert all(r.success for r in result.execution_results)
