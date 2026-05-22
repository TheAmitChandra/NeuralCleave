"""
Unit tests for WorkflowRecommender, WorkflowOutcome, and WorkflowRecommendation.
"""

from __future__ import annotations

import pytest

from app.core.learning.recommender import (
    WorkflowOutcome,
    WorkflowRecommendation,
    WorkflowRecommender,
)


# ---------------------------------------------------------------------------
# WorkflowOutcome
# ---------------------------------------------------------------------------

class TestWorkflowOutcome:
    def test_attributes(self):
        o = WorkflowOutcome(workflow_type="analytics", success=True, duration=5.0)
        assert o.workflow_type == "analytics"
        assert o.success is True
        assert o.duration == 5.0

    def test_metadata_defaults_empty(self):
        o = WorkflowOutcome(workflow_type="x", success=False, duration=1.0)
        assert o.metadata == {}


# ---------------------------------------------------------------------------
# WorkflowRecommendation
# ---------------------------------------------------------------------------

class TestWorkflowRecommendation:
    def test_to_dict_keys(self):
        rec = WorkflowRecommendation(
            recommendation_id="r1", workflow_type="analytics",
            reason="high success", confidence=0.9,
        )
        d = rec.to_dict()
        for key in ("recommendation_id", "workflow_type", "reason", "confidence", "metadata"):
            assert key in d

    def test_values_preserved(self):
        rec = WorkflowRecommendation(
            recommendation_id="r1", workflow_type="wt",
            reason="reason", confidence=0.75,
        )
        d = rec.to_dict()
        assert d["workflow_type"] == "wt"
        assert d["confidence"] == 0.75


# ---------------------------------------------------------------------------
# WorkflowRecommender — construction
# ---------------------------------------------------------------------------

class TestRecommenderInit:
    def test_empty_on_init(self):
        r = WorkflowRecommender()
        assert r.workflow_type_count == 0
        assert r.outcome_count() == 0

    def test_recommend_empty_returns_empty(self):
        r = WorkflowRecommender()
        assert r.recommend() == []

    def test_top_workflows_empty_returns_empty(self):
        r = WorkflowRecommender()
        assert r.top_workflows() == []


# ---------------------------------------------------------------------------
# record_outcome
# ---------------------------------------------------------------------------

class TestRecordOutcome:
    def test_returns_workflow_outcome(self):
        r = WorkflowRecommender()
        o = r.record_outcome("analytics", True, 2.0)
        assert isinstance(o, WorkflowOutcome)

    def test_increments_counts(self):
        r = WorkflowRecommender()
        r.record_outcome("analytics", True, 1.0)
        r.record_outcome("analytics", False, 2.0)
        assert r.outcome_count("analytics") == 2
        assert r.outcome_count() == 2

    def test_negative_duration_raises(self):
        r = WorkflowRecommender()
        with pytest.raises(ValueError, match="duration"):
            r.record_outcome("wt", True, -1.0)

    def test_zero_duration_accepted(self):
        r = WorkflowRecommender()
        o = r.record_outcome("wt", True, 0.0)
        assert o.duration == 0.0

    def test_multiple_workflow_types(self):
        r = WorkflowRecommender()
        r.record_outcome("analytics", True, 1.0)
        r.record_outcome("reporting", True, 2.0)
        assert r.workflow_type_count == 2

    def test_with_metadata(self):
        r = WorkflowRecommender()
        o = r.record_outcome("wt", True, 1.0, metadata={"env": "prod"})
        assert o.metadata["env"] == "prod"


# ---------------------------------------------------------------------------
# success_rate / average_duration
# ---------------------------------------------------------------------------

class TestIntrospection:
    def test_success_rate_all_success(self):
        r = WorkflowRecommender()
        for _ in range(4):
            r.record_outcome("wt", True, 1.0)
        assert r.success_rate("wt") == pytest.approx(1.0)

    def test_success_rate_mixed(self):
        r = WorkflowRecommender()
        r.record_outcome("wt", True, 1.0)
        r.record_outcome("wt", False, 1.0)
        assert r.success_rate("wt") == pytest.approx(0.5)

    def test_success_rate_unknown_type(self):
        r = WorkflowRecommender()
        assert r.success_rate("ghost") == 0.0

    def test_average_duration(self):
        r = WorkflowRecommender()
        r.record_outcome("wt", True, 2.0)
        r.record_outcome("wt", True, 4.0)
        assert r.average_duration("wt") == pytest.approx(3.0)

    def test_average_duration_unknown_type(self):
        r = WorkflowRecommender()
        assert r.average_duration("ghost") == 0.0

    def test_outcome_count_filtered(self):
        r = WorkflowRecommender()
        r.record_outcome("a", True, 1.0)
        r.record_outcome("a", True, 1.0)
        r.record_outcome("b", True, 1.0)
        assert r.outcome_count("a") == 2
        assert r.outcome_count("b") == 1
        assert r.outcome_count() == 3


# ---------------------------------------------------------------------------
# recommend
# ---------------------------------------------------------------------------

class TestRecommend:
    def test_recommend_single_type(self):
        r = WorkflowRecommender()
        r.record_outcome("analytics", True, 1.0)
        recs = r.recommend()
        assert len(recs) == 1
        assert recs[0].workflow_type == "analytics"

    def test_recommend_sorted_by_confidence_desc(self):
        r = WorkflowRecommender()
        # high success
        for _ in range(9):
            r.record_outcome("good-wf", True, 1.0)
        r.record_outcome("good-wf", False, 1.0)
        # low success
        for _ in range(2):
            r.record_outcome("bad-wf", True, 1.0)
        for _ in range(8):
            r.record_outcome("bad-wf", False, 1.0)
        recs = r.recommend()
        assert recs[0].workflow_type == "good-wf"
        assert recs[0].confidence > recs[1].confidence

    def test_recommend_respects_top_n(self):
        r = WorkflowRecommender()
        for wtype in ["a", "b", "c", "d", "e", "f"]:
            r.record_outcome(wtype, True, 1.0)
        recs = r.recommend(top_n=3)
        assert len(recs) == 3

    def test_recommend_with_context_does_not_raise(self):
        r = WorkflowRecommender()
        r.record_outcome("wt", True, 1.0)
        recs = r.recommend(context={"user": "admin"})
        assert len(recs) == 1

    def test_confidence_in_valid_range(self):
        r = WorkflowRecommender()
        r.record_outcome("wt", True, 2.0)
        r.record_outcome("wt", False, 5.0)
        recs = r.recommend()
        for rec in recs:
            assert 0.0 <= rec.confidence <= 1.0

    def test_reason_contains_rate(self):
        r = WorkflowRecommender()
        r.record_outcome("wt", True, 1.0)
        r.record_outcome("wt", True, 1.0)
        recs = r.recommend()
        assert "100%" in recs[0].reason or "2/2" in recs[0].reason

    def test_recommendation_ids_unique(self):
        r = WorkflowRecommender()
        r.record_outcome("a", True, 1.0)
        r.record_outcome("b", True, 1.0)
        recs = r.recommend()
        ids = [rec.recommendation_id for rec in recs]
        assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# top_workflows
# ---------------------------------------------------------------------------

class TestTopWorkflows:
    def test_returns_strings(self):
        r = WorkflowRecommender()
        r.record_outcome("analytics", True, 1.0)
        r.record_outcome("reporting", True, 2.0)
        tops = r.top_workflows()
        assert all(isinstance(t, str) for t in tops)

    def test_top_n_respected(self):
        r = WorkflowRecommender()
        for wtype in ["a", "b", "c", "d"]:
            r.record_outcome(wtype, True, 1.0)
        assert len(r.top_workflows(n=2)) == 2

    def test_best_workflow_is_first(self):
        r = WorkflowRecommender()
        for _ in range(9):
            r.record_outcome("winner", True, 0.1)
        r.record_outcome("winner", False, 0.1)
        for _ in range(5):
            r.record_outcome("loser", False, 10.0)
        r.record_outcome("loser", True, 10.0)
        assert r.top_workflows(n=1)[0] == "winner"


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_resets_all(self):
        r = WorkflowRecommender()
        r.record_outcome("wt", True, 1.0)
        r.clear()
        assert r.workflow_type_count == 0
        assert r.outcome_count() == 0
        assert r.recommend() == []
