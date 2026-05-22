"""Tests for SpanRecorder — local in-memory span tracing."""

from __future__ import annotations

import pytest

from app.core.observability.span_recorder import (
    SpanEvent,
    SpanRecord,
    SpanRecorder,
    _ActiveSpan,
)


# ===========================================================================
# TestSpanEvent
# ===========================================================================

class TestSpanEvent:
    def test_to_dict(self) -> None:
        ev = SpanEvent(name="search.started", timestamp=100.0, attributes={"k": "v"})
        d = ev.to_dict()
        assert d["name"] == "search.started"
        assert d["timestamp"] == 100.0
        assert d["attributes"] == {"k": "v"}

    def test_default_attributes(self) -> None:
        ev = SpanEvent(name="ev", timestamp=0.0)
        assert ev.attributes == {}


# ===========================================================================
# TestSpanRecord
# ===========================================================================

class TestSpanRecord:
    def _make_record(self) -> SpanRecord:
        return SpanRecord(
            span_id="abc123",
            trace_id="trace001",
            name="tool.execute",
            start_time=100.0,
            end_time=100.5,
        )

    def test_duration_seconds(self) -> None:
        rec = self._make_record()
        assert rec.duration_seconds == pytest.approx(0.5)

    def test_to_dict_keys(self) -> None:
        rec = self._make_record()
        d = rec.to_dict()
        for key in ("span_id", "trace_id", "name", "start_time", "end_time",
                    "duration_seconds", "attributes", "events", "status"):
            assert key in d

    def test_to_dict_duration(self) -> None:
        rec = self._make_record()
        assert rec.to_dict()["duration_seconds"] == pytest.approx(0.5)

    def test_default_status_is_unset(self) -> None:
        rec = self._make_record()
        assert rec.status == "unset"


# ===========================================================================
# TestSpanRecorderBasic
# ===========================================================================

class TestSpanRecorderBasic:
    def test_empty_recorder_has_no_spans(self) -> None:
        r = SpanRecorder()
        assert r.total_spans == 0

    def test_start_span_records_one_span(self) -> None:
        r = SpanRecorder()
        with r.start_span("op.test"):
            pass
        assert r.total_spans == 1

    def test_span_name_is_recorded(self) -> None:
        r = SpanRecorder()
        with r.start_span("my.operation"):
            pass
        assert r.finished_spans()[0].name == "my.operation"

    def test_span_has_valid_ids(self) -> None:
        r = SpanRecorder()
        with r.start_span("op"):
            pass
        span = r.finished_spans()[0]
        assert len(span.span_id) == 16
        assert len(span.trace_id) == 32

    def test_multiple_spans_share_trace_id(self) -> None:
        r = SpanRecorder()
        with r.start_span("op1"):
            pass
        with r.start_span("op2"):
            pass
        spans = r.finished_spans()
        assert spans[0].trace_id == spans[1].trace_id

    def test_custom_trace_id(self) -> None:
        r = SpanRecorder()
        with r.start_span("op", trace_id="custom-trace"):
            pass
        assert r.finished_spans()[0].trace_id == "custom-trace"

    def test_parent_span_id(self) -> None:
        r = SpanRecorder()
        with r.start_span("child", parent_span_id="parent-123"):
            pass
        assert r.finished_spans()[0].parent_span_id == "parent-123"


# ===========================================================================
# TestSpanAttributes
# ===========================================================================

class TestSpanAttributes:
    def test_attributes_passed_on_start(self) -> None:
        r = SpanRecorder()
        with r.start_span("op", attributes={"tool": "shell"}):
            pass
        assert r.finished_spans()[0].attributes["tool"] == "shell"

    def test_set_attribute_inside_span(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as span:
            span.set_attribute("result", "success")
        assert r.finished_spans()[0].attributes["result"] == "success"

    def test_multiple_attributes(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as span:
            span.set_attribute("a", 1)
            span.set_attribute("b", "two")
        rec = r.finished_spans()[0]
        assert rec.attributes["a"] == 1
        assert rec.attributes["b"] == "two"


# ===========================================================================
# TestSpanEvents
# ===========================================================================

class TestSpanEvents:
    def test_add_event_recorded(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as span:
            span.add_event("step.started")
        rec = r.finished_spans()[0]
        assert len(rec.events) == 1
        assert rec.events[0].name == "step.started"

    def test_add_event_with_attributes(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as span:
            span.add_event("query.done", {"rows": 42})
        rec = r.finished_spans()[0]
        assert rec.events[0].attributes["rows"] == 42

    def test_multiple_events_ordered(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as span:
            span.add_event("e1")
            span.add_event("e2")
        events = r.finished_spans()[0].events
        assert [e.name for e in events] == ["e1", "e2"]


# ===========================================================================
# TestSpanStatus
# ===========================================================================

class TestSpanStatus:
    def test_default_status_ok_after_success(self) -> None:
        r = SpanRecorder()
        with r.start_span("op"):
            pass
        assert r.finished_spans()[0].status == "ok"

    def test_set_status_ok(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as span:
            span.set_status_ok()
        assert r.finished_spans()[0].status == "ok"

    def test_exception_sets_error_status(self) -> None:
        r = SpanRecorder()
        with pytest.raises(RuntimeError):
            with r.start_span("op"):
                raise RuntimeError("boom")
        assert r.finished_spans()[0].status == "error"
        assert "boom" in r.finished_spans()[0].error

    def test_set_status_error_manually(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as span:
            span.set_status_error("custom error")
        assert r.finished_spans()[0].status == "error"
        assert r.finished_spans()[0].error == "custom error"


# ===========================================================================
# TestSpanRecorderQuery
# ===========================================================================

class TestSpanRecorderQuery:
    def test_finished_spans_filter_by_name(self) -> None:
        r = SpanRecorder()
        with r.start_span("a"):
            pass
        with r.start_span("b"):
            pass
        with r.start_span("a"):
            pass
        assert r.span_count("a") == 2
        assert r.span_count("b") == 1

    def test_find_span_returns_most_recent(self) -> None:
        r = SpanRecorder()
        with r.start_span("op") as s:
            s.set_attribute("idx", 1)
        with r.start_span("op") as s:
            s.set_attribute("idx", 2)
        span = r.find_span("op")
        assert span.attributes["idx"] == 2

    def test_find_span_returns_none_when_not_found(self) -> None:
        r = SpanRecorder()
        assert r.find_span("nonexistent") is None

    def test_reset_clears_spans(self) -> None:
        r = SpanRecorder()
        with r.start_span("op"):
            pass
        r.reset()
        assert r.total_spans == 0

    def test_reset_resets_trace_id(self) -> None:
        r = SpanRecorder()
        with r.start_span("op"):
            pass
        old_trace = r.finished_spans()[0].trace_id
        r.reset()
        with r.start_span("op"):
            pass
        new_trace = r.finished_spans()[0].trace_id
        assert old_trace != new_trace

    def test_max_spans_evicts_oldest(self) -> None:
        r = SpanRecorder(max_spans=3)
        for i in range(5):
            with r.start_span(f"op-{i}"):
                pass
        assert r.total_spans == 3
        assert r.finished_spans()[0].name == "op-2"
