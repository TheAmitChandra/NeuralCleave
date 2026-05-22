"""
Unit tests for FeedbackCollector, FeedbackEntry, and RewardCalculator.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.core.learning.feedback import FeedbackEntry, FeedbackCollector, RewardCalculator


# ---------------------------------------------------------------------------
# FeedbackEntry
# ---------------------------------------------------------------------------

class TestFeedbackEntry:
    def test_to_dict_keys(self):
        entry = FeedbackEntry(
            entry_id="e1", agent_id="planner", task_id="t1",
            feedback_type="explicit", score=0.8,
        )
        d = entry.to_dict()
        for key in ("entry_id", "agent_id", "task_id", "feedback_type", "score", "timestamp", "metadata"):
            assert key in d

    def test_score_preserved(self):
        entry = FeedbackEntry(entry_id="e", agent_id="a", task_id="t", feedback_type="implicit", score=0.5)
        assert entry.to_dict()["score"] == 0.5

    def test_timestamp_iso_format(self):
        entry = FeedbackEntry(entry_id="e", agent_id="a", task_id="t", feedback_type="implicit", score=0.0)
        datetime.fromisoformat(entry.to_dict()["timestamp"])

    def test_metadata_defaults_empty(self):
        entry = FeedbackEntry(entry_id="e", agent_id="a", task_id="t", feedback_type="explicit", score=1.0)
        assert entry.to_dict()["metadata"] == {}


# ---------------------------------------------------------------------------
# RewardCalculator
# ---------------------------------------------------------------------------

class TestRewardCalculator:
    def _exec(self, success: bool):
        m = MagicMock()
        m.success = success
        return m

    def _val(self, confidence: float, issues: list):
        m = MagicMock()
        m.confidence = confidence
        m.issues = issues
        return m

    def test_successful_no_validation(self):
        calc = RewardCalculator()
        score = calc.calculate(self._exec(True), None)
        # 0.6 + 0.3*0.5 = 0.75
        assert abs(score - 0.75) < 1e-6

    def test_failed_no_validation(self):
        calc = RewardCalculator()
        score = calc.calculate(self._exec(False), None)
        # 0 + 0.3*0.5 = 0.15
        assert abs(score - 0.15) < 1e-6

    def test_successful_with_perfect_validation(self):
        calc = RewardCalculator()
        score = calc.calculate(self._exec(True), self._val(1.0, []))
        # 0.6 + 0.3*1.0 = 0.9
        assert abs(score - 0.9) < 1e-6

    def test_penalty_for_issues(self):
        calc = RewardCalculator()
        score = calc.calculate(self._exec(True), self._val(1.0, ["issue1", "issue2"]))
        # 0.6 + 0.3 - 0.1*2 = 0.7
        assert abs(score - 0.7) < 1e-6

    def test_score_clamped_to_zero(self):
        calc = RewardCalculator()
        score = calc.calculate(self._exec(False), self._val(0.0, ["a", "b", "c", "d", "e", "f"]))
        assert score == 0.0

    def test_score_clamped_to_one(self):
        calc = RewardCalculator(success_weight=0.8, accuracy_weight=0.8, penalty_weight=0.0)
        score = calc.calculate(self._exec(True), self._val(1.0, []))
        assert score == 1.0

    def test_custom_weights(self):
        calc = RewardCalculator(success_weight=1.0, accuracy_weight=0.0, penalty_weight=0.0)
        score = calc.calculate(self._exec(True), None)
        assert score == 1.0


# ---------------------------------------------------------------------------
# FeedbackCollector — construction
# ---------------------------------------------------------------------------

class TestFeedbackCollectorInit:
    def test_empty_on_init(self):
        fc = FeedbackCollector()
        assert fc.entry_count == 0

    def test_average_score_empty_returns_zero(self):
        fc = FeedbackCollector()
        assert fc.average_score() == 0.0


# ---------------------------------------------------------------------------
# FeedbackCollector — record
# ---------------------------------------------------------------------------

class TestFeedbackCollectorRecord:
    def test_record_returns_entry(self):
        fc = FeedbackCollector()
        entry = fc.record("planner", "t1", 0.9)
        assert isinstance(entry, FeedbackEntry)

    def test_record_increments_count(self):
        fc = FeedbackCollector()
        fc.record("a", "t", 0.5)
        fc.record("a", "t", 0.7)
        assert fc.entry_count == 2

    def test_record_explicit_type(self):
        fc = FeedbackCollector()
        entry = fc.record("a", "t", 0.8, feedback_type="explicit")
        assert entry.feedback_type == "explicit"

    def test_record_invalid_type_raises(self):
        fc = FeedbackCollector()
        with pytest.raises(ValueError, match="feedback_type"):
            fc.record("a", "t", 0.5, feedback_type="unknown")

    def test_record_score_below_zero_raises(self):
        fc = FeedbackCollector()
        with pytest.raises(ValueError, match="score"):
            fc.record("a", "t", -0.1)

    def test_record_score_above_one_raises(self):
        fc = FeedbackCollector()
        with pytest.raises(ValueError, match="score"):
            fc.record("a", "t", 1.1)

    def test_record_boundary_scores(self):
        fc = FeedbackCollector()
        fc.record("a", "t1", 0.0)
        fc.record("a", "t2", 1.0)
        assert fc.entry_count == 2

    def test_record_with_metadata(self):
        fc = FeedbackCollector()
        entry = fc.record("a", "t", 0.6, metadata={"source": "user"})
        assert entry.metadata["source"] == "user"

    def test_record_unique_entry_ids(self):
        fc = FeedbackCollector()
        e1 = fc.record("a", "t", 0.5)
        e2 = fc.record("a", "t", 0.5)
        assert e1.entry_id != e2.entry_id


# ---------------------------------------------------------------------------
# FeedbackCollector — get_feedback
# ---------------------------------------------------------------------------

class TestGetFeedback:
    def test_get_all(self):
        fc = FeedbackCollector()
        fc.record("agent-a", "t1", 0.5)
        fc.record("agent-b", "t2", 0.7)
        assert len(fc.get_feedback()) == 2

    def test_filter_by_agent(self):
        fc = FeedbackCollector()
        fc.record("agent-a", "t1", 0.5)
        fc.record("agent-b", "t2", 0.7)
        fc.record("agent-a", "t3", 0.9)
        results = fc.get_feedback(agent_id="agent-a")
        assert len(results) == 2
        assert all(e.agent_id == "agent-a" for e in results)

    def test_filter_by_task(self):
        fc = FeedbackCollector()
        fc.record("a", "t1", 0.5)
        fc.record("b", "t1", 0.6)
        fc.record("c", "t2", 0.7)
        results = fc.get_feedback(task_id="t1")
        assert len(results) == 2

    def test_filter_by_agent_and_task(self):
        fc = FeedbackCollector()
        fc.record("a", "t1", 0.5)
        fc.record("a", "t2", 0.6)
        fc.record("b", "t1", 0.7)
        results = fc.get_feedback(agent_id="a", task_id="t1")
        assert len(results) == 1

    def test_filter_returns_empty_for_unknown_agent(self):
        fc = FeedbackCollector()
        fc.record("a", "t", 0.5)
        assert fc.get_feedback(agent_id="unknown") == []


# ---------------------------------------------------------------------------
# FeedbackCollector — average_score
# ---------------------------------------------------------------------------

class TestAverageScore:
    def test_average_all_agents(self):
        fc = FeedbackCollector()
        fc.record("a", "t1", 0.4)
        fc.record("b", "t2", 0.6)
        assert abs(fc.average_score() - 0.5) < 1e-6

    def test_average_single_agent(self):
        fc = FeedbackCollector()
        fc.record("a", "t1", 0.8)
        fc.record("a", "t2", 0.6)
        fc.record("b", "t3", 0.2)
        assert abs(fc.average_score(agent_id="a") - 0.7) < 1e-6

    def test_average_no_entries_for_agent(self):
        fc = FeedbackCollector()
        fc.record("a", "t", 0.5)
        assert fc.average_score(agent_id="unknown") == 0.0


# ---------------------------------------------------------------------------
# FeedbackCollector — clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_removes_all_entries(self):
        fc = FeedbackCollector()
        fc.record("a", "t", 0.5)
        fc.record("b", "t", 0.7)
        fc.clear()
        assert fc.entry_count == 0

    def test_clear_resets_average(self):
        fc = FeedbackCollector()
        fc.record("a", "t", 0.9)
        fc.clear()
        assert fc.average_score() == 0.0
