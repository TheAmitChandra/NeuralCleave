"""
test_router_agent.py — Unit tests for RouterAgent (router.py) and
                        ExecutorAgent (executor.py)
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.orchestration.executor import ExecutionResult, ExecutorAgent
from app.core.orchestration.planner import Plan, PlannerAgent, SubTask
from app.core.orchestration.router import RoutingDecision, RouterAgent


# ---------------------------------------------------------------------------
# TestRoutingDecision
# ---------------------------------------------------------------------------


class TestRoutingDecision:
    def test_to_dict_keys(self):
        rd = RoutingDecision(
            task_id="t1", assigned_agent_type="executor", priority=5, reason="default"
        )
        d = rd.to_dict()
        assert set(d.keys()) == {
            "task_id", "assigned_agent_type", "priority", "reason", "metadata"
        }

    def test_to_dict_values(self):
        rd = RoutingDecision(
            task_id="t2", assigned_agent_type="planner", priority=3, reason="keyword"
        )
        d = rd.to_dict()
        assert d["task_id"] == "t2"
        assert d["assigned_agent_type"] == "planner"
        assert d["priority"] == 3

    def test_metadata_default_empty(self):
        rd = RoutingDecision(task_id="t", assigned_agent_type="x", priority=1, reason="r")
        assert rd.metadata == {}


# ---------------------------------------------------------------------------
# TestRouterAgent
# ---------------------------------------------------------------------------


class TestRouterAgent:
    def _agent(self) -> RouterAgent:
        return RouterAgent(agent_id="router-1")

    def test_default_agent_id_assigned(self):
        agent = RouterAgent()
        assert agent.agent_id
        assert len(agent.agent_id) == 36

    def test_custom_agent_id(self):
        agent = RouterAgent(agent_id="r99")
        assert agent.agent_id == "r99"

    def test_register_worker_stores_capabilities(self):
        agent = self._agent()
        agent.register_worker("analysis_agent", ["analyze", "summarize"])
        workers = agent.get_workers()
        assert "analysis_agent" in workers
        assert "analyze" in workers["analysis_agent"]

    def test_register_worker_adds_routing_keywords(self):
        agent = self._agent()
        agent.register_worker("search_agent", ["search", "find"])
        table = agent.get_routing_table()
        assert table["search"] == "search_agent"
        assert table["find"] == "search_agent"

    def test_register_worker_empty_type_raises(self):
        agent = self._agent()
        with pytest.raises(ValueError):
            agent.register_worker("", ["something"])

    def test_add_route(self):
        agent = self._agent()
        agent.add_route("VALIDATE", "validator_agent")
        assert agent.get_routing_table()["validate"] == "validator_agent"

    def test_get_routing_table_returns_copy(self):
        agent = self._agent()
        agent.add_route("test", "tester")
        table = agent.get_routing_table()
        table["extra"] = "should not affect internal"
        assert "extra" not in agent.get_routing_table()

    async def test_route_default_fallback(self):
        agent = self._agent()
        task = SubTask(task_id="t1", description="unknown task")
        decision = await agent.route_single(task)
        assert decision.assigned_agent_type == RouterAgent.DEFAULT_AGENT_TYPE
        assert "fallback" in decision.reason

    async def test_route_keyword_match(self):
        agent = self._agent()
        agent.add_route("search", "search_agent")
        task = SubTask(task_id="t1", description="search the web for news")
        decision = await agent.route_single(task)
        assert decision.assigned_agent_type == "search_agent"
        assert "keyword" in decision.reason

    async def test_route_payload_hint(self):
        agent = self._agent()
        task = SubTask(
            task_id="t1",
            description="do a thing",
            payload={"agent_type": "specialist_agent"},
        )
        decision = await agent.route_single(task)
        assert decision.assigned_agent_type == "specialist_agent"
        assert "payload" in decision.reason

    async def test_route_explicit_assignment_overrides_all(self):
        agent = self._agent()
        agent.add_route("search", "search_agent")  # would match keyword
        task = SubTask(
            task_id="t1",
            description="search the web",
            assigned_to="custom_agent",
        )
        decision = await agent.route_single(task)
        assert decision.assigned_agent_type == "custom_agent"
        assert "explicitly" in decision.reason

    async def test_route_full_plan(self):
        agent = self._agent()
        agent.add_route("fetch", "fetch_agent")
        plan = Plan(plan_id="p1", goal="test plan")
        plan.add_subtask(SubTask(task_id="t1", description="fetch data"))
        plan.add_subtask(SubTask(task_id="t2", description="process data"))
        decisions = await agent.route(plan)
        assert len(decisions) == 2
        assert decisions[0].assigned_agent_type == "fetch_agent"
        assert decisions[1].assigned_agent_type == RouterAgent.DEFAULT_AGENT_TYPE

    async def test_route_empty_plan(self):
        agent = self._agent()
        plan = Plan(plan_id="p0", goal="empty")
        decisions = await agent.route(plan)
        assert decisions == []


# ---------------------------------------------------------------------------
# TestExecutionResult
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_to_dict_keys(self):
        r = ExecutionResult(task_id="t1", success=True)
        assert set(r.to_dict().keys()) == {
            "task_id", "success", "output", "duration_seconds", "error", "metadata"
        }

    def test_to_dict_success(self):
        r = ExecutionResult(task_id="t1", success=True, output="hello")
        d = r.to_dict()
        assert d["success"] is True
        assert d["output"] == "hello"
        assert d["error"] is None


# ---------------------------------------------------------------------------
# TestExecutorAgent
# ---------------------------------------------------------------------------


class TestExecutorAgent:
    def test_default_agent_id_assigned(self):
        agent = ExecutorAgent()
        assert agent.agent_id
        assert len(agent.agent_id) == 36

    def test_custom_timeout(self):
        agent = ExecutorAgent(default_timeout=60.0)
        assert agent.default_timeout == 60.0

    async def test_execute_no_handler_returns_success(self):
        agent = ExecutorAgent()
        task = SubTask(task_id="t1", description="run something")
        result = await agent.execute(task)
        assert result.success is True
        assert result.task_id == "t1"
        assert result.output == {"executed": "run something"}
        assert result.error is None

    async def test_execute_with_registered_handler(self):
        agent = ExecutorAgent()

        async def my_handler(task, registry):
            return {"result": "handled"}

        agent.register_handler("my_type", my_handler)
        task = SubTask(
            task_id="t2", description="typed task", payload={"task_type": "my_type"}
        )
        result = await agent.execute(task)
        assert result.success is True
        assert result.output == {"result": "handled"}

    async def test_execute_handler_exception_captured(self):
        agent = ExecutorAgent()

        async def bad_handler(task, registry):
            raise RuntimeError("something broke")

        agent.register_handler("fail_type", bad_handler)
        task = SubTask(
            task_id="t3", description="fail", payload={"task_type": "fail_type"}
        )
        result = await agent.execute(task)
        assert result.success is False
        assert "something broke" in (result.error or "")

    async def test_execute_timeout(self):
        agent = ExecutorAgent()

        async def slow_handler(task, registry):
            await asyncio.sleep(10)
            return "done"

        agent.register_handler("slow", slow_handler)
        task = SubTask(task_id="t4", description="slow", payload={"task_type": "slow"})
        result = await agent.execute(task, timeout=0.05)
        assert result.success is False
        assert "timed out" in (result.error or "").lower()

    async def test_execute_batch_parallel(self):
        agent = ExecutorAgent()
        tasks = [SubTask(task_id=f"t{i}", description=f"task {i}") for i in range(5)]
        results = await agent.execute_batch(tasks, parallel=True)
        assert len(results) == 5
        assert all(r.success for r in results)

    async def test_execute_batch_sequential(self):
        agent = ExecutorAgent()
        tasks = [SubTask(task_id=f"t{i}", description=f"task {i}") for i in range(3)]
        results = await agent.execute_batch(tasks, parallel=False)
        assert len(results) == 3
        assert all(r.success for r in results)

    async def test_execute_duration_recorded(self):
        agent = ExecutorAgent()
        task = SubTask(task_id="t1", description="quick task")
        result = await agent.execute(task)
        assert result.duration_seconds >= 0.0

    def test_register_handler_retrievable(self):
        agent = ExecutorAgent()

        async def h(t, r):
            return None

        agent.register_handler("mytype", h)
        assert agent.get_handler("mytype") is h

    def test_get_handler_unknown_returns_none(self):
        agent = ExecutorAgent()
        assert agent.get_handler("unknown") is None
