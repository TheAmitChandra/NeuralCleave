"""
Unit tests for FailurePatternDetector, FailureRecord, and FailurePattern.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.learning.failure_detector import (
    FailurePattern,
    FailurePatternDetector,
    FailureRecord,
)

# ---------------------------------------------------------------------------
# FailureRecord
# ---------------------------------------------------------------------------


class TestFailureRecord:
    def test_to_dict_keys(self):
        rec = FailureRecord(record_id="r1", agent_id="executor", task_id="t1", error="timeout")
        d = rec.to_dict()
        for key in ("record_id", "agent_id", "task_id", "error", "context", "timestamp"):
            assert key in d

    def test_error_preserved(self):
        rec = FailureRecord(record_id="r", agent_id="a", task_id="t", error="oops")
        assert rec.to_dict()["error"] == "oops"

    def test_context_defaults_empty(self):
        rec = FailureRecord(record_id="r", agent_id="a", task_id="t", error="e")
        assert rec.to_dict()["context"] == {}

    def test_timestamp_iso_format(self):
        rec = FailureRecord(record_id="r", agent_id="a", task_id="t", error="e")
        datetime.fromisoformat(rec.to_dict()["timestamp"])


# ---------------------------------------------------------------------------
# FailurePattern
# ---------------------------------------------------------------------------


class TestFailurePattern:
    def _make(self) -> FailurePattern:
        return FailurePattern(
            pattern_id="p1",
            description="timeout",
            occurrences=5,
            agent_ids=["executor", "planner"],
            last_seen=datetime.now(),
        )

    def test_to_dict_structure(self):
        p = self._make()
        d = p.to_dict()
        assert d["pattern_id"] == "p1"
        assert d["description"] == "timeout"
        assert d["occurrences"] == 5
        assert "executor" in d["agent_ids"]
        assert "timestamp" not in d  # uses last_seen key
        assert "last_seen" in d


# ---------------------------------------------------------------------------
# FailurePatternDetector — construction
# ---------------------------------------------------------------------------


class TestDetectorInit:
    def test_default_threshold(self):
        det = FailurePatternDetector()
        assert det.default_threshold == 2

    def test_custom_threshold(self):
        det = FailurePatternDetector(default_threshold=3)
        assert det.default_threshold == 3

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            FailurePatternDetector(default_threshold=0)

    def test_initial_counts_zero(self):
        det = FailurePatternDetector()
        assert det.record_count == 0
        assert det.pattern_count == 0


# ---------------------------------------------------------------------------
# record_failure
# ---------------------------------------------------------------------------


class TestRecordFailure:
    def test_returns_failure_record(self):
        det = FailurePatternDetector()
        rec = det.record_failure("executor", "t1", "timeout")
        assert isinstance(rec, FailureRecord)

    def test_increments_record_count(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t1", "err")
        det.record_failure("a", "t2", "err")
        assert det.record_count == 2

    def test_distinct_errors_increment_pattern_count(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t1", "timeout")
        det.record_failure("a", "t2", "connection reset")
        assert det.pattern_count == 2

    def test_same_error_same_pattern(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t1", "timeout")
        det.record_failure("b", "t2", "timeout")
        assert det.pattern_count == 1

    def test_normalises_case(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t1", "Timeout")
        det.record_failure("a", "t2", "TIMEOUT")
        assert det.pattern_count == 1
        assert det.record_count == 2

    def test_normalises_whitespace(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t1", "  timeout  ")
        det.record_failure("a", "t2", "timeout")
        assert det.pattern_count == 1

    def test_record_with_context(self):
        det = FailurePatternDetector()
        rec = det.record_failure("a", "t", "err", context={"code": 500})
        assert rec.context["code"] == 500

    def test_unique_record_ids(self):
        det = FailurePatternDetector()
        r1 = det.record_failure("a", "t1", "err")
        r2 = det.record_failure("a", "t2", "err")
        assert r1.record_id != r2.record_id


# ---------------------------------------------------------------------------
# detect_patterns
# ---------------------------------------------------------------------------


class TestDetectPatterns:
    def test_no_patterns_below_threshold(self):
        det = FailurePatternDetector(default_threshold=3)
        det.record_failure("a", "t1", "timeout")
        det.record_failure("a", "t2", "timeout")
        assert det.detect_patterns() == []

    def test_pattern_detected_at_threshold(self):
        det = FailurePatternDetector(default_threshold=2)
        det.record_failure("a", "t1", "timeout")
        det.record_failure("b", "t2", "timeout")
        patterns = det.detect_patterns()
        assert len(patterns) == 1
        assert patterns[0].occurrences == 2

    def test_custom_threshold_override(self):
        det = FailurePatternDetector(default_threshold=5)
        det.record_failure("a", "t1", "err")
        det.record_failure("a", "t2", "err")
        # Override threshold to 2
        patterns = det.detect_patterns(threshold=2)
        assert len(patterns) == 1

    def test_patterns_sorted_by_occurrences_desc(self):
        det = FailurePatternDetector(default_threshold=1)
        for _ in range(5):
            det.record_failure("a", "tx", "error-a")
        for _ in range(2):
            det.record_failure("b", "ty", "error-b")
        patterns = det.detect_patterns(threshold=1)
        assert patterns[0].occurrences >= patterns[1].occurrences

    def test_pattern_collects_all_agents(self):
        det = FailurePatternDetector(default_threshold=2)
        det.record_failure("agent-1", "t1", "crash")
        det.record_failure("agent-2", "t2", "crash")
        patterns = det.detect_patterns()
        agent_ids = patterns[0].agent_ids
        assert "agent-1" in agent_ids
        assert "agent-2" in agent_ids

    def test_stable_pattern_id(self):
        det = FailurePatternDetector(default_threshold=2)
        det.record_failure("a", "t1", "err")
        det.record_failure("a", "t2", "err")
        p1 = det.detect_patterns()[0].pattern_id
        det.record_failure("a", "t3", "err")
        p2 = det.detect_patterns()[0].pattern_id
        assert p1 == p2

    def test_multiple_distinct_patterns(self):
        det = FailurePatternDetector(default_threshold=2)
        for _ in range(3):
            det.record_failure("a", "tx", "timeout")
        for _ in range(2):
            det.record_failure("b", "ty", "oom")
        patterns = det.detect_patterns()
        assert len(patterns) == 2


# ---------------------------------------------------------------------------
# get_records
# ---------------------------------------------------------------------------


class TestGetRecords:
    def test_get_all_records(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t1", "e")
        det.record_failure("b", "t2", "e")
        assert len(det.get_records()) == 2

    def test_filter_by_agent(self):
        det = FailurePatternDetector()
        det.record_failure("agent-a", "t1", "err")
        det.record_failure("agent-b", "t2", "err")
        det.record_failure("agent-a", "t3", "err")
        recs = det.get_records(agent_id="agent-a")
        assert len(recs) == 2
        assert all(r.agent_id == "agent-a" for r in recs)

    def test_filter_unknown_agent(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t", "e")
        assert det.get_records(agent_id="ghost") == []


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_resets_all(self):
        det = FailurePatternDetector()
        det.record_failure("a", "t", "err")
        det.clear()
        assert det.record_count == 0
        assert det.pattern_count == 0
        assert det.detect_patterns() == []
