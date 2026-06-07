"""
test_planner_agent.py — Unit tests for PlannerAgent (planner.py)
"""

from __future__ import annotations

import pytest

from app.core.orchestration.planner import (
    Plan,
    PlanDecompositionError,
    PlannerAgent,
    SubTask,
)

# ---------------------------------------------------------------------------
# TestSubTask
# ---------------------------------------------------------------------------


class TestSubTask:
    def test_defaults(self):
        st = SubTask(task_id="t1", description="do something")
        assert st.dependencies == []
        assert st.assigned_to is None
        assert st.payload == {}
        assert st.priority == 5

    def test_custom_fields(self):
        st = SubTask(
            task_id="t2",
            description="run tests",
            dependencies=["t1"],
            assigned_to="executor",
            payload={"k": "v"},
            priority=1,
        )
        assert st.dependencies == ["t1"]
        assert st.assigned_to == "executor"
        assert st.payload == {"k": "v"}
        assert st.priority == 1

    def test_to_dict_keys(self):
        st = SubTask(task_id="x", description="x")
        d = st.to_dict()
        assert set(d.keys()) == {
            "task_id",
            "description",
            "dependencies",
            "assigned_to",
            "payload",
            "priority",
        }

    def test_to_dict_values(self):
        st = SubTask(task_id="abc", description="hello", priority=3)
        d = st.to_dict()
        assert d["task_id"] == "abc"
        assert d["description"] == "hello"
        assert d["priority"] == 3


# ---------------------------------------------------------------------------
# TestPlan
# ---------------------------------------------------------------------------


class TestPlan:
    def _make_plan(self) -> Plan:
        return Plan(plan_id="p1", goal="achieve goal")

    def test_add_subtask(self):
        plan = self._make_plan()
        st = SubTask(task_id="t1", description="step 1")
        plan.add_subtask(st)
        assert len(plan.subtasks) == 1

    def test_get_subtask_found(self):
        plan = self._make_plan()
        st = SubTask(task_id="t1", description="step 1")
        plan.add_subtask(st)
        assert plan.get_subtask("t1") is st

    def test_get_subtask_not_found(self):
        plan = self._make_plan()
        assert plan.get_subtask("missing") is None

    def test_execution_order_empty(self):
        plan = self._make_plan()
        assert plan.execution_order() == []

    def test_execution_order_no_deps(self):
        plan = self._make_plan()
        for i in range(3):
            plan.add_subtask(SubTask(task_id=f"t{i}", description=f"task {i}"))
        order = plan.execution_order()
        # All tasks independent → one batch of 3
        assert len(order) == 1
        assert len(order[0]) == 3

    def test_execution_order_sequential(self):
        plan = self._make_plan()
        t0 = SubTask(task_id="t0", description="first")
        t1 = SubTask(task_id="t1", description="second", dependencies=["t0"])
        t2 = SubTask(task_id="t2", description="third", dependencies=["t1"])
        plan.add_subtask(t0)
        plan.add_subtask(t1)
        plan.add_subtask(t2)
        order = plan.execution_order()
        assert len(order) == 3
        assert order[0][0].task_id == "t0"
        assert order[1][0].task_id == "t1"
        assert order[2][0].task_id == "t2"

    def test_execution_order_parallel_batches(self):
        # t0 → t2
        # t1 → t2  (t0 and t1 can run in parallel, then t2)
        plan = self._make_plan()
        t0 = SubTask(task_id="t0", description="a")
        t1 = SubTask(task_id="t1", description="b")
        t2 = SubTask(task_id="t2", description="c", dependencies=["t0", "t1"])
        plan.add_subtask(t0)
        plan.add_subtask(t1)
        plan.add_subtask(t2)
        order = plan.execution_order()
        assert len(order) == 2
        batch0_ids = {t.task_id for t in order[0]}
        assert batch0_ids == {"t0", "t1"}
        assert order[1][0].task_id == "t2"

    def test_execution_order_circular_raises(self):
        plan = self._make_plan()
        t0 = SubTask(task_id="t0", description="a", dependencies=["t1"])
        t1 = SubTask(task_id="t1", description="b", dependencies=["t0"])
        plan.add_subtask(t0)
        plan.add_subtask(t1)
        with pytest.raises(ValueError, match="Circular dependency"):
            plan.execution_order()

    def test_to_dict_keys(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert set(d.keys()) == {"plan_id", "goal", "subtasks", "metadata"}


# ---------------------------------------------------------------------------
# TestPlannerAgent
# ---------------------------------------------------------------------------


class TestPlannerAgent:
    def test_default_agent_id_assigned(self):
        agent = PlannerAgent()
        assert agent.agent_id
        assert len(agent.agent_id) == 36  # UUID4 format

    def test_custom_agent_id(self):
        agent = PlannerAgent(agent_id="planner-1")
        assert agent.agent_id == "planner-1"

    async def test_plan_simple_goal(self):
        agent = PlannerAgent()
        plan = await agent.plan("do something")
        assert plan.goal == "do something"
        assert len(plan.subtasks) == 1
        assert plan.subtasks[0].description == "do something"

    async def test_plan_numbered_list(self):
        agent = PlannerAgent()
        goal = "1. fetch data\n2. process data\n3. save results"
        plan = await agent.plan(goal)
        assert len(plan.subtasks) == 3
        assert plan.subtasks[0].description == "fetch data"
        assert plan.subtasks[2].description == "save results"

    async def test_plan_bulleted_list(self):
        agent = PlannerAgent()
        goal = "- step A\n- step B"
        plan = await agent.plan(goal)
        assert len(plan.subtasks) == 2

    async def test_plan_sequential_context(self):
        agent = PlannerAgent()
        goal = "- step A\n- step B\n- step C"
        plan = await agent.plan(goal, context={"sequential": True})
        order = plan.execution_order()
        assert len(order) == 3  # must be strictly sequential

    async def test_plan_empty_goal_raises(self):
        agent = PlannerAgent()
        with pytest.raises(PlanDecompositionError, match="empty"):
            await agent.plan("")

    async def test_plan_whitespace_goal_raises(self):
        agent = PlannerAgent()
        with pytest.raises(PlanDecompositionError, match="empty"):
            await agent.plan("   ")

    async def test_plan_stores_in_history(self):
        agent = PlannerAgent()
        plan = await agent.plan("do work")
        retrieved = agent.get_plan(plan.plan_id)
        assert retrieved is plan

    async def test_get_plan_unknown_returns_none(self):
        agent = PlannerAgent()
        assert agent.get_plan("does-not-exist") is None

    async def test_plan_count_increments(self):
        agent = PlannerAgent()
        assert agent.plan_count == 0
        await agent.plan("task one")
        await agent.plan("task two")
        assert agent.plan_count == 2

    async def test_max_subtasks_exceeded_raises(self):
        agent = PlannerAgent(max_subtasks=2)
        goal = "1. a\n2. b\n3. c"
        with pytest.raises(PlanDecompositionError, match="limit"):
            await agent.plan(goal)

    async def test_plan_metadata_contains_context(self):
        agent = PlannerAgent()
        plan = await agent.plan("do X", context={"env": "prod"})
        assert plan.metadata["context"]["env"] == "prod"

    async def test_plan_metadata_contains_planner_id(self):
        agent = PlannerAgent(agent_id="p99")
        plan = await agent.plan("do Y")
        assert plan.metadata["planner_id"] == "p99"

    async def test_priority_from_context(self):
        agent = PlannerAgent()
        plan = await agent.plan("- task A", context={"priority": 1})
        assert plan.subtasks[0].priority == 1
