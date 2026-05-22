"""
test_critic_agent.py — Unit tests for CriticAgent (critic.py)
"""
from __future__ import annotations

import pytest

from app.core.orchestration.critic import CriticAgent, CritiqueScore, PlanCritique
from app.core.orchestration.executor import ExecutionResult
from app.core.orchestration.planner import Plan, SubTask
from app.core.orchestration.validator import ValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(tid: str = "t1") -> SubTask:
    return SubTask(task_id=tid, description="do something")


def _ok(tid: str = "t1", output: object = "result") -> ExecutionResult:
    return ExecutionResult(task_id=tid, success=True, output=output)


def _fail(tid: str = "t1", error: str = "boom") -> ExecutionResult:
    return ExecutionResult(task_id=tid, success=False, error=error)


def _valid(tid: str = "t1") -> ValidationResult:
    return ValidationResult(task_id=tid, valid=True, confidence=1.0, recommendation="accept")


def _invalid(tid: str = "t1", issues: list[str] | None = None) -> ValidationResult:
    return ValidationResult(
        task_id=tid,
        valid=False,
        confidence=0.0,
        issues=issues or ["execution failed"],
        recommendation="retry",
    )


# ---------------------------------------------------------------------------
# TestCritiqueScore
# ---------------------------------------------------------------------------


class TestCritiqueScore:
    def test_to_dict_keys(self):
        cs = CritiqueScore(task_id="t1", quality_score=80.0, completeness=1.0, accuracy=1.0)
        d = cs.to_dict()
        assert set(d.keys()) == {
            "task_id", "quality_score", "completeness", "accuracy",
            "issues", "recommendations", "metadata",
        }

    def test_to_dict_values(self):
        cs = CritiqueScore(
            task_id="t1", quality_score=75.0, completeness=0.8, accuracy=0.9
        )
        d = cs.to_dict()
        assert d["quality_score"] == 75.0
        assert d["completeness"] == 0.8

    def test_issues_default_empty(self):
        cs = CritiqueScore(task_id="t1", quality_score=100.0, completeness=1.0, accuracy=1.0)
        assert cs.issues == []
        assert cs.recommendations == []


# ---------------------------------------------------------------------------
# TestPlanCritique
# ---------------------------------------------------------------------------


class TestPlanCritique:
    def test_to_dict_keys(self):
        pc = PlanCritique(plan_id="p1", overall_score=85.0)
        d = pc.to_dict()
        assert set(d.keys()) == {
            "plan_id", "overall_score", "task_scores", "summary", "recommendations"
        }


# ---------------------------------------------------------------------------
# TestCriticAgent
# ---------------------------------------------------------------------------


class TestCriticAgent:
    def test_default_agent_id(self):
        agent = CriticAgent()
        assert agent.agent_id
        assert len(agent.agent_id) == 36

    def test_custom_agent_id(self):
        agent = CriticAgent(agent_id="critic-1")
        assert agent.agent_id == "critic-1"

    def test_custom_quality_threshold(self):
        agent = CriticAgent(quality_threshold=80.0)
        assert agent.quality_threshold == 80.0

    async def test_critique_valid_successful_result(self):
        agent = CriticAgent()
        score = await agent.critique(_task(), _ok(), _valid())
        assert score.quality_score > 0
        assert score.accuracy == 1.0
        assert score.completeness == 1.0
        assert score.issues == []

    async def test_critique_failed_result(self):
        agent = CriticAgent()
        score = await agent.critique(_task(), _fail(), _invalid())
        assert score.accuracy == 0.0
        assert score.completeness == 0.0
        assert score.quality_score == 0.0

    async def test_critique_incomplete_output_string(self):
        agent = CriticAgent()
        empty_output = ExecutionResult(task_id="t1", success=True, output="")
        score = await agent.critique(_task(), empty_output, _valid())
        assert score.completeness == 0.0
        assert any("incomplete" in i.lower() for i in score.issues)

    async def test_critique_none_output_partial_completeness(self):
        agent = CriticAgent()
        none_output = ExecutionResult(task_id="t1", success=True, output=None)
        score = await agent.critique(_task(), none_output, _valid())
        assert score.completeness == 0.5

    async def test_critique_empty_list_output(self):
        agent = CriticAgent()
        list_output = ExecutionResult(task_id="t1", success=True, output=[])
        score = await agent.critique(_task(), list_output, _valid())
        assert score.completeness == 0.3

    async def test_critique_dict_output_non_empty(self):
        agent = CriticAgent()
        dict_output = ExecutionResult(task_id="t1", success=True, output={"k": "v"})
        score = await agent.critique(_task(), dict_output, _valid())
        assert score.completeness == 1.0

    async def test_critique_issues_from_validation(self):
        agent = CriticAgent()
        validation = _invalid(issues=["schema mismatch"])
        score = await agent.critique(_task(), _ok(), validation)
        assert "schema mismatch" in score.issues

    async def test_critique_error_in_result_adds_issue(self):
        agent = CriticAgent()
        result = ExecutionResult(task_id="t1", success=False, error="network timeout")
        score = await agent.critique(_task(), result, _invalid())
        assert any("network timeout" in i for i in score.issues)
        assert any("fix" in r.lower() for r in score.recommendations)

    async def test_quality_score_is_between_0_and_100(self):
        agent = CriticAgent()
        for output in ["text", [], {}, None, ""]:
            result = ExecutionResult(task_id="t1", success=True, output=output)
            score = await agent.critique(_task(), result, _valid())
            assert 0.0 <= score.quality_score <= 100.0

    async def test_meets_threshold_true(self):
        agent = CriticAgent(quality_threshold=70.0)
        score = await agent.critique(_task(), _ok(), _valid())
        assert agent.meets_threshold(score)

    async def test_meets_threshold_false(self):
        agent = CriticAgent(quality_threshold=70.0)
        score = await agent.critique(_task(), _fail(), _invalid())
        assert not agent.meets_threshold(score)

    async def test_critique_plan_all_valid(self):
        agent = CriticAgent()
        plan = Plan(plan_id="p1", goal="goal")
        for i in range(3):
            plan.add_subtask(SubTask(task_id=f"t{i}", description=f"task {i}"))

        results = [_ok(f"t{i}") for i in range(3)]
        validations = [_valid(f"t{i}") for i in range(3)]
        critique = await agent.critique_plan(plan, results, validations)

        assert critique.plan_id == "p1"
        assert critique.overall_score > 0
        assert len(critique.task_scores) == 3

    async def test_critique_plan_mixed_results(self):
        agent = CriticAgent()
        plan = Plan(plan_id="p2", goal="mixed")
        plan.add_subtask(SubTask(task_id="t0", description="good task"))
        plan.add_subtask(SubTask(task_id="t1", description="bad task"))

        results = [_ok("t0"), _fail("t1")]
        validations = [_valid("t0"), _invalid("t1")]
        critique = await agent.critique_plan(plan, results, validations)

        assert 0.0 <= critique.overall_score <= 100.0
        assert len(critique.task_scores) == 2

    async def test_critique_plan_empty_results(self):
        agent = CriticAgent()
        plan = Plan(plan_id="p3", goal="empty")
        plan.add_subtask(SubTask(task_id="t0", description="task"))
        # No results or validations for t0
        critique = await agent.critique_plan(plan, [], [])
        assert critique.overall_score == 0.0
        assert critique.task_scores == []

    async def test_critique_plan_summary_contains_score(self):
        agent = CriticAgent(quality_threshold=50.0)
        plan = Plan(plan_id="p4", goal="plan")
        plan.add_subtask(SubTask(task_id="t0", description="task"))
        results = [_ok("t0")]
        validations = [_valid("t0")]
        critique = await agent.critique_plan(plan, results, validations)
        assert str(int(critique.overall_score)) in critique.summary or "." in critique.summary

    async def test_critique_plan_to_dict(self):
        agent = CriticAgent()
        plan = Plan(plan_id="p5", goal="x")
        plan.add_subtask(SubTask(task_id="t0", description="x"))
        critique = await agent.critique_plan(plan, [_ok("t0")], [_valid("t0")])
        d = critique.to_dict()
        assert d["plan_id"] == "p5"
        assert "task_scores" in d
