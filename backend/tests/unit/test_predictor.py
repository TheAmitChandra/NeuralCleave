"""
Unit tests for WorkflowPredictor, StateTransition, and ActionPrediction.
"""

from __future__ import annotations

import pytest

from app.core.learning.predictor import (
    StateTransition,
    ActionPrediction,
    WorkflowPredictor,
)


# ---------------------------------------------------------------------------
# StateTransition
# ---------------------------------------------------------------------------

class TestStateTransition:
    def test_to_dict_keys(self):
        t = StateTransition(from_state="idle", action="plan", to_state="planning", success=True)
        d = t.to_dict()
        for key in ("from_state", "action", "to_state", "success", "metadata"):
            assert key in d

    def test_values_preserved(self):
        t = StateTransition(from_state="a", action="b", to_state="c", success=False)
        d = t.to_dict()
        assert d["from_state"] == "a"
        assert d["action"] == "b"
        assert d["to_state"] == "c"
        assert d["success"] is False

    def test_metadata_defaults_empty(self):
        t = StateTransition(from_state="a", action="b", to_state="c", success=True)
        assert t.to_dict()["metadata"] == {}


# ---------------------------------------------------------------------------
# ActionPrediction
# ---------------------------------------------------------------------------

class TestActionPrediction:
    def test_to_dict(self):
        pred = ActionPrediction(action="execute", confidence=0.8, from_state="planning")
        d = pred.to_dict()
        assert d["action"] == "execute"
        assert d["confidence"] == 0.8
        assert d["from_state"] == "planning"

    def test_metadata_in_dict(self):
        pred = ActionPrediction(action="x", confidence=0.5, from_state="s", metadata={"note": "y"})
        assert pred.to_dict()["metadata"]["note"] == "y"


# ---------------------------------------------------------------------------
# WorkflowPredictor — construction
# ---------------------------------------------------------------------------

class TestPredictorInit:
    def test_empty_on_init(self):
        p = WorkflowPredictor()
        assert p.transition_count == 0
        assert p.known_states() == []

    def test_predict_unknown_state_returns_none(self):
        p = WorkflowPredictor()
        assert p.predict_next_action("unknown") is None

    def test_predict_risk_unknown_returns_half(self):
        p = WorkflowPredictor()
        assert p.predict_risk("x", "y") == 0.5


# ---------------------------------------------------------------------------
# record_transition
# ---------------------------------------------------------------------------

class TestRecordTransition:
    def test_returns_state_transition(self):
        p = WorkflowPredictor()
        t = p.record_transition("idle", "plan", "planning", success=True)
        assert isinstance(t, StateTransition)

    def test_increments_count(self):
        p = WorkflowPredictor()
        p.record_transition("a", "act", "b", success=True)
        p.record_transition("a", "act", "c", success=False)
        assert p.transition_count == 2

    def test_registers_state(self):
        p = WorkflowPredictor()
        p.record_transition("idle", "plan", "planning", success=True)
        assert "idle" in p.known_states()

    def test_with_metadata(self):
        p = WorkflowPredictor()
        t = p.record_transition("s", "a", "s2", success=True, metadata={"tag": "x"})
        assert t.metadata["tag"] == "x"


# ---------------------------------------------------------------------------
# predict_next_action
# ---------------------------------------------------------------------------

class TestPredictNextAction:
    def test_single_action_predicts_it(self):
        p = WorkflowPredictor()
        p.record_transition("idle", "plan", "planning", success=True)
        pred = p.predict_next_action("idle")
        assert pred is not None
        assert pred.action == "plan"

    def test_predicts_most_frequent_action(self):
        p = WorkflowPredictor()
        p.record_transition("s", "common", "s2", success=True)
        p.record_transition("s", "common", "s2", success=True)
        p.record_transition("s", "rare", "s3", success=True)
        pred = p.predict_next_action("s")
        assert pred.action == "common"

    def test_confidence_is_one_for_single_action(self):
        p = WorkflowPredictor()
        for _ in range(5):
            p.record_transition("s", "act", "s2", success=True)
        pred = p.predict_next_action("s")
        assert pred.confidence == pytest.approx(1.0)

    def test_confidence_reflects_frequency(self):
        p = WorkflowPredictor()
        p.record_transition("s", "a", "s2", success=True)
        p.record_transition("s", "a", "s2", success=True)
        p.record_transition("s", "b", "s3", success=True)
        # a: 2/3, b: 1/3
        pred = p.predict_next_action("s")
        assert pred.confidence == pytest.approx(2 / 3)

    def test_from_state_matches(self):
        p = WorkflowPredictor()
        p.record_transition("alpha", "go", "beta", success=True)
        pred = p.predict_next_action("alpha")
        assert pred.from_state == "alpha"

    def test_unknown_state_returns_none(self):
        p = WorkflowPredictor()
        p.record_transition("s", "a", "s2", success=True)
        assert p.predict_next_action("other") is None


# ---------------------------------------------------------------------------
# predict_risk
# ---------------------------------------------------------------------------

class TestPredictRisk:
    def test_all_success_risk_zero(self):
        p = WorkflowPredictor()
        for _ in range(5):
            p.record_transition("s", "a", "s2", success=True)
        assert p.predict_risk("s", "a") == pytest.approx(0.0)

    def test_all_failure_risk_one(self):
        p = WorkflowPredictor()
        for _ in range(3):
            p.record_transition("s", "a", "s2", success=False)
        assert p.predict_risk("s", "a") == pytest.approx(1.0)

    def test_mixed_risk(self):
        p = WorkflowPredictor()
        p.record_transition("s", "a", "s2", success=True)
        p.record_transition("s", "a", "s2", success=False)
        # 1 success / 2 total → failure rate = 0.5
        assert p.predict_risk("s", "a") == pytest.approx(0.5)

    def test_unknown_pair_returns_half(self):
        p = WorkflowPredictor()
        assert p.predict_risk("unknown", "act") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# get_transitions / known_states
# ---------------------------------------------------------------------------

class TestIntrospection:
    def test_get_all_transitions(self):
        p = WorkflowPredictor()
        p.record_transition("s", "a", "s2", success=True)
        p.record_transition("s", "b", "s3", success=False)
        assert len(p.get_transitions()) == 2

    def test_get_transitions_filtered(self):
        p = WorkflowPredictor()
        p.record_transition("alpha", "a", "beta", success=True)
        p.record_transition("gamma", "b", "delta", success=True)
        p.record_transition("alpha", "c", "epsilon", success=False)
        results = p.get_transitions(from_state="alpha")
        assert len(results) == 2
        assert all(t.from_state == "alpha" for t in results)

    def test_known_states_all_recorded(self):
        p = WorkflowPredictor()
        p.record_transition("s1", "a", "s2", success=True)
        p.record_transition("s3", "b", "s4", success=False)
        states = p.known_states()
        assert "s1" in states
        assert "s3" in states


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_resets_all(self):
        p = WorkflowPredictor()
        p.record_transition("s", "a", "s2", success=True)
        p.clear()
        assert p.transition_count == 0
        assert p.known_states() == []
        assert p.predict_next_action("s") is None
        assert p.predict_risk("s", "a") == 0.5
