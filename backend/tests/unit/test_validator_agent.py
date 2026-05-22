"""
test_validator_agent.py — Unit tests for ValidatorAgent (validator.py)
"""
from __future__ import annotations

import pytest

from app.core.orchestration.executor import ExecutionResult
from app.core.orchestration.planner import SubTask
from app.core.orchestration.validator import ValidationResult, ValidatorAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(task_id: str = "t1") -> SubTask:
    return SubTask(task_id=task_id, description="do something")


def _ok(task_id: str = "t1", output: object = "output") -> ExecutionResult:
    return ExecutionResult(task_id=task_id, success=True, output=output)


def _fail(task_id: str = "t1", error: str = "boom") -> ExecutionResult:
    return ExecutionResult(task_id=task_id, success=False, error=error)


# ---------------------------------------------------------------------------
# TestValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_to_dict_keys(self):
        vr = ValidationResult(task_id="t1", valid=True, confidence=1.0)
        d = vr.to_dict()
        assert set(d.keys()) == {
            "task_id", "valid", "confidence", "issues",
            "recommendation", "metadata",
        }

    def test_to_dict_valid(self):
        vr = ValidationResult(task_id="t1", valid=True, confidence=0.9, recommendation="accept")
        d = vr.to_dict()
        assert d["valid"] is True
        assert d["confidence"] == 0.9
        assert d["recommendation"] == "accept"

    def test_to_dict_invalid_with_issues(self):
        vr = ValidationResult(
            task_id="t2", valid=False, confidence=0.0,
            issues=["it broke"], recommendation="retry"
        )
        d = vr.to_dict()
        assert d["valid"] is False
        assert "it broke" in d["issues"]

    def test_issues_default_empty(self):
        vr = ValidationResult(task_id="t1", valid=True, confidence=1.0)
        assert vr.issues == []


# ---------------------------------------------------------------------------
# TestValidatorAgent
# ---------------------------------------------------------------------------


class TestValidatorAgent:
    def test_default_agent_id_assigned(self):
        agent = ValidatorAgent()
        assert agent.agent_id
        assert len(agent.agent_id) == 36

    def test_custom_agent_id(self):
        agent = ValidatorAgent(agent_id="val-1")
        assert agent.agent_id == "val-1"

    def test_custom_confidence_threshold(self):
        agent = ValidatorAgent(confidence_threshold=0.9)
        assert agent.confidence_threshold == 0.9

    async def test_validate_success_no_issues(self):
        agent = ValidatorAgent()
        result = await agent.validate(_task(), _ok())
        assert result.valid is True
        assert result.issues == []
        assert result.recommendation == "accept"
        assert result.confidence == 1.0

    async def test_validate_failed_result(self):
        agent = ValidatorAgent()
        result = await agent.validate(_task(), _fail())
        assert result.valid is False
        assert any("failed" in i.lower() for i in result.issues)
        assert result.confidence == 0.0

    async def test_validate_success_no_output(self):
        agent = ValidatorAgent()
        result = await agent.validate(
            _task(), ExecutionResult(task_id="t1", success=True, output=None)
        )
        assert result.valid is False
        assert any("no output" in i.lower() for i in result.issues)

    async def test_validate_custom_rule_adds_no_issues(self):
        agent = ValidatorAgent()

        async def always_ok(task, result):
            return []

        agent.add_rule(always_ok)
        vr = await agent.validate(_task(), _ok())
        assert vr.valid is True

    async def test_validate_custom_rule_adds_issues(self):
        agent = ValidatorAgent()

        async def always_fail(task, result):
            return ["custom issue"]

        agent.add_rule(always_fail)
        vr = await agent.validate(_task(), _ok())
        assert "custom issue" in vr.issues
        assert vr.valid is False

    async def test_validate_rule_exception_becomes_issue(self):
        agent = ValidatorAgent()

        async def bad_rule(task, result):
            raise RuntimeError("rule exploded")

        agent.add_rule(bad_rule)
        vr = await agent.validate(_task(), _ok())
        assert any("rule exploded" in i for i in vr.issues)

    async def test_validate_recommendation_accept(self):
        agent = ValidatorAgent(confidence_threshold=0.7)
        vr = await agent.validate(_task(), _ok())
        assert vr.recommendation == "accept"

    async def test_validate_recommendation_retry(self):
        agent = ValidatorAgent()
        # One issue → confidence 0.8 → above 0.3 but not valid → retry
        async def one_issue(task, result):
            return ["minor issue"]

        agent.add_rule(one_issue)
        vr = await agent.validate(_task(), _ok())
        assert vr.recommendation == "retry"

    async def test_validate_recommendation_escalate_many_issues(self):
        agent = ValidatorAgent()

        async def three_issues(task, result):
            return ["issue1", "issue2", "issue3"]

        agent.add_rule(three_issues)
        vr = await agent.validate(_task(), _ok())
        assert vr.recommendation == "escalate"

    async def test_validate_recommendation_escalate_failed(self):
        # failed → confidence 0.0 < 0.3 → escalate
        agent = ValidatorAgent()
        vr = await agent.validate(_task(), _fail())
        assert vr.recommendation == "escalate"

    async def test_validate_batch_returns_all(self):
        agent = ValidatorAgent()
        pairs = [
            (_task("t1"), _ok("t1")),
            (_task("t2"), _fail("t2")),
        ]
        results = await agent.validate_batch(pairs)
        assert len(results) == 2
        assert results[0].valid is True
        assert results[1].valid is False

    def test_add_and_remove_rule(self):
        agent = ValidatorAgent()

        async def rule(t, r):
            return []

        agent.add_rule(rule)
        assert agent.rule_count == 1
        agent.remove_rule(rule)
        assert agent.rule_count == 0

    def test_remove_nonexistent_rule_is_noop(self):
        agent = ValidatorAgent()

        async def rule(t, r):
            return []

        agent.remove_rule(rule)  # should not raise
        assert agent.rule_count == 0

    async def test_confidence_decreases_per_issue(self):
        agent = ValidatorAgent()

        async def two_issues(task, result):
            return ["a", "b"]

        agent.add_rule(two_issues)
        vr = await agent.validate(_task(), _ok())
        # 1.0 - 2*0.2 = 0.6
        assert abs(vr.confidence - 0.6) < 1e-9

    async def test_task_id_propagated(self):
        agent = ValidatorAgent()
        vr = await agent.validate(_task("abc"), _ok("abc"))
        assert vr.task_id == "abc"
