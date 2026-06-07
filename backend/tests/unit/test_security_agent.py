"""
test_security_agent.py — Unit tests for SecurityAgent (security_agent.py)
"""

from __future__ import annotations

import pytest

from app.core.orchestration.planner import Plan, SubTask
from app.core.orchestration.security_agent import (
    PlanRiskReport,
    RiskAssessment,
    SecurityAgent,
    _level_from_score,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(tid: str = "t1", desc: str = "run a query", priority: int = 5) -> SubTask:
    return SubTask(task_id=tid, description=desc, priority=priority)


# ---------------------------------------------------------------------------
# TestLevelFromScore
# ---------------------------------------------------------------------------


class TestLevelFromScore:
    def test_low(self):
        assert _level_from_score(0.0) == "low"
        assert _level_from_score(25.0) == "low"

    def test_medium(self):
        assert _level_from_score(26.0) == "medium"
        assert _level_from_score(60.0) == "medium"

    def test_high(self):
        assert _level_from_score(61.0) == "high"
        assert _level_from_score(85.0) == "high"

    def test_critical(self):
        assert _level_from_score(86.0) == "critical"
        assert _level_from_score(100.0) == "critical"


# ---------------------------------------------------------------------------
# TestRiskAssessment
# ---------------------------------------------------------------------------


class TestRiskAssessment:
    def test_to_dict_keys(self):
        ra = RiskAssessment(task_id="t1", risk_score=30.0, risk_level="medium")
        d = ra.to_dict()
        assert set(d.keys()) == {
            "task_id",
            "risk_score",
            "risk_level",
            "risk_factors",
            "blocked",
            "recommendation",
            "metadata",
        }

    def test_to_dict_values(self):
        ra = RiskAssessment(task_id="t1", risk_score=90.0, risk_level="critical", blocked=True)
        d = ra.to_dict()
        assert d["blocked"] is True
        assert d["risk_score"] == 90.0


# ---------------------------------------------------------------------------
# TestPlanRiskReport
# ---------------------------------------------------------------------------


class TestPlanRiskReport:
    def test_to_dict_keys(self):
        report = PlanRiskReport(plan_id="p1")
        d = report.to_dict()
        assert set(d.keys()) == {
            "plan_id",
            "assessments",
            "overall_risk_score",
            "blocked_count",
            "summary",
        }


# ---------------------------------------------------------------------------
# TestSecurityAgent
# ---------------------------------------------------------------------------


class TestSecurityAgent:
    def test_default_agent_id(self):
        agent = SecurityAgent()
        assert len(agent.agent_id) == 36

    def test_custom_agent_id(self):
        agent = SecurityAgent(agent_id="sec-1")
        assert agent.agent_id == "sec-1"

    def test_custom_block_threshold(self):
        agent = SecurityAgent(block_threshold=50.0)
        assert agent.block_threshold == 50.0

    async def test_assess_safe_task(self):
        agent = SecurityAgent()
        result = await agent.assess(_task(desc="fetch public API data"))
        assert result.risk_level == "low"
        assert result.blocked is False
        assert result.recommendation == "proceed"

    async def test_assess_dangerous_keyword_delete(self):
        agent = SecurityAgent()
        result = await agent.assess(_task(desc="delete all records from the database"))
        assert result.risk_score > 0
        assert any("delete" in f for f in result.risk_factors)

    async def test_assess_multiple_keywords_capped(self):
        agent = SecurityAgent()
        # delete(15) + drop(15) + sudo(15) + exec(15) + eval(15) = 75 but capped at 45
        result = await agent.assess(_task(desc="sudo exec eval drop delete everything"))
        assert result.risk_score <= 45.0

    async def test_assess_payload_override(self):
        agent = SecurityAgent()
        task = SubTask(task_id="t1", description="safe description", payload={"risk_score": 90.0})
        result = await agent.assess(task)
        assert result.risk_score == 90.0
        assert result.blocked is True

    async def test_assess_high_priority_adds_bonus(self):
        agent = SecurityAgent()
        low_priority = await agent.assess(_task(priority=5))
        high_priority = await agent.assess(_task(priority=1))
        assert high_priority.risk_score >= low_priority.risk_score

    async def test_assess_blocked_when_above_threshold(self):
        agent = SecurityAgent(block_threshold=10.0)
        result = await agent.assess(_task(desc="delete files"))
        assert result.blocked is True
        assert result.recommendation == "block"

    async def test_assess_recommendation_review(self):
        agent = SecurityAgent()
        task = SubTask(task_id="t1", description="safe", payload={"risk_score": 65.0})
        result = await agent.assess(task)
        assert result.recommendation == "review"

    async def test_assess_custom_rule_adds_risk(self):
        agent = SecurityAgent()

        async def always_risky(task):
            return 20.0, "custom risk factor"

        agent.add_rule(always_risky)
        result = await agent.assess(_task(desc="safe task"))
        assert result.risk_score >= 20.0
        assert "custom risk factor" in result.risk_factors

    async def test_assess_custom_rule_exception_logged(self):
        agent = SecurityAgent()

        async def broken_rule(task):
            raise RuntimeError("rule failed")

        agent.add_rule(broken_rule)
        result = await agent.assess(_task())
        assert any("rule error" in f for f in result.risk_factors)

    async def test_assess_risk_score_clamped_0_100(self):
        agent = SecurityAgent()
        task = SubTask(task_id="t1", description="x", payload={"risk_score": 150.0})
        result = await agent.assess(task)
        assert result.risk_score == 100.0

    async def test_add_remove_rule(self):
        agent = SecurityAgent()

        async def rule(t):
            return 0.0, ""

        agent.add_rule(rule)
        assert agent.rule_count == 1
        agent.remove_rule(rule)
        assert agent.rule_count == 0

    async def test_assess_plan_all_safe(self):
        agent = SecurityAgent()
        plan = Plan(plan_id="p1", goal="safe plan")
        for i in range(3):
            plan.add_subtask(SubTask(task_id=f"t{i}", description="get data"))
        report = await agent.assess_plan(plan)
        assert report.blocked_count == 0
        assert "safe" in report.summary

    async def test_assess_plan_with_blocked_task(self):
        agent = SecurityAgent(block_threshold=10.0)
        plan = Plan(plan_id="p2", goal="risky plan")
        plan.add_subtask(SubTask(task_id="t0", description="delete database"))
        plan.add_subtask(SubTask(task_id="t1", description="get data"))
        report = await agent.assess_plan(plan)
        assert report.blocked_count >= 1

    async def test_assess_plan_empty(self):
        agent = SecurityAgent()
        plan = Plan(plan_id="p3", goal="empty")
        report = await agent.assess_plan(plan)
        assert report.overall_risk_score == 0.0
        assert report.assessments == []

    async def test_plan_risk_report_to_dict(self):
        agent = SecurityAgent()
        plan = Plan(plan_id="p4", goal="x")
        plan.add_subtask(SubTask(task_id="t0", description="safe task"))
        report = await agent.assess_plan(plan)
        d = report.to_dict()
        assert d["plan_id"] == "p4"
        assert isinstance(d["assessments"], list)

    async def test_assess_task_id_propagated(self):
        agent = SecurityAgent()
        result = await agent.assess(_task(tid="abc-123"))
        assert result.task_id == "abc-123"
