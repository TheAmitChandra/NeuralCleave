"""Span Recorder — local in-memory distributed tracing for CortexFlow.

Provides a lightweight span recording layer that works independently of
the OpenTelemetry SDK.  Useful for:
    - local development and debugging (no OTel collector required)
    - unit tests that need to assert on span attributes / events
    - fallback instrumentation when ``opentelemetry-sdk`` is unavailable

Usage::

    recorder = SpanRecorder()
    with recorder.start_span("tool.execute", attributes={"tool": "search"}) as span:
        span.add_event("search.started")
        result = do_search()
        span.add_event("search.finished", {"result_count": len(result)})

    spans = recorder.finished_spans()
    assert spans[0].name == "tool.execute"
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SpanEvent:
    """A timestamped event recorded inside a span."""

    name: str
    timestamp: float
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "attributes": dict(self.attributes),
        }


@dataclass
class SpanRecord:
    """An immutable record of a completed span.

    Attributes:
        span_id:        Unique identifier for this span.
        trace_id:       Identifier shared across all spans in a trace.
        parent_span_id: ID of the parent span, or ``None`` for root spans.
        name:           Operation name.
        start_time:     Unix timestamp when the span started.
        end_time:       Unix timestamp when the span finished.
        attributes:     Key-value pairs attached to the span.
        events:         Timestamped events within the span.
        status:         "ok" | "error" | "unset".
        error:          Error message if status is "error".
    """

    span_id: str
    trace_id: str
    name: str
    start_time: float
    end_time: float
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    status: str = "unset"
    error: str = ""
    parent_span_id: str | None = None

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "attributes": dict(self.attributes),
            "events": [e.to_dict() for e in self.events],
            "status": self.status,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Mutable span builder (used inside context manager)
# ---------------------------------------------------------------------------

class _ActiveSpan:
    """Mutable span that can be configured before it is closed."""

    def __init__(
        self,
        name: str,
        trace_id: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self.span_id = uuid.uuid4().hex[:16]
        self.trace_id = trace_id
        self.parent_span_id = parent_span_id
        self.name = name
        self.start_time = time.time()
        self._attributes: dict[str, Any] = dict(attributes or {})
        self._events: list[SpanEvent] = []
        self._status = "unset"
        self._error = ""

    def set_attribute(self, key: str, value: Any) -> None:
        """Attach a key-value attribute to this span."""
        self._attributes[key] = value

    def add_event(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> None:
        """Record a timestamped event within this span."""
        self._events.append(
            SpanEvent(name=name, timestamp=time.time(), attributes=attributes or {})
        )

    def set_status_ok(self) -> None:
        self._status = "ok"

    def set_status_error(self, message: str = "") -> None:
        self._status = "error"
        self._error = message

    def finish(self) -> SpanRecord:
        if self._status == "unset":
            self._status = "ok"
        return SpanRecord(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            name=self.name,
            start_time=self.start_time,
            end_time=time.time(),
            attributes=dict(self._attributes),
            events=list(self._events),
            status=self._status,
            error=self._error,
        )


# ---------------------------------------------------------------------------
# SpanRecorder
# ---------------------------------------------------------------------------

class SpanRecorder:
    """Records spans to an in-memory list.

    Thread-safe for single-threaded use (no locking).

    Parameters:
        max_spans: Maximum number of finished spans to retain.
                   Oldest spans are discarded when the limit is reached.
    """

    def __init__(self, max_spans: int = 1000) -> None:
        self._max = max_spans
        self._finished: list[SpanRecord] = []
        self._active_trace_id: str | None = None

    # ------------------------------------------------------------------
    # Context manager API
    # ------------------------------------------------------------------

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[_ActiveSpan, None, None]:
        """Start a new span, yield the mutable ``_ActiveSpan``, then record it.

        If ``trace_id`` is omitted, the current active trace ID is reused;
        if there is none, a new trace ID is generated.
        """
        tid = trace_id or self._active_trace_id or uuid.uuid4().hex
        if self._active_trace_id is None:
            self._active_trace_id = tid

        span = _ActiveSpan(
            name=name,
            trace_id=tid,
            parent_span_id=parent_span_id,
            attributes=attributes,
        )
        try:
            yield span
        except Exception as exc:
            span.set_status_error(str(exc))
            raise
        finally:
            record = span.finish()
            self._record(record)

    def _record(self, span: SpanRecord) -> None:
        if len(self._finished) >= self._max:
            self._finished.pop(0)
        self._finished.append(span)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def finished_spans(self, name: str | None = None) -> list[SpanRecord]:
        """Return all finished spans, optionally filtered by operation name."""
        if name is None:
            return list(self._finished)
        return [s for s in self._finished if s.name == name]

    def find_span(self, name: str) -> SpanRecord | None:
        """Return the most recent span matching *name*, or None."""
        for span in reversed(self._finished):
            if span.name == name:
                return span
        return None

    def span_count(self, name: str | None = None) -> int:
        """Return the number of recorded spans (optionally filtered by name)."""
        return len(self.finished_spans(name))

    def reset(self) -> None:
        """Clear all recorded spans and reset the active trace ID."""
        self._finished.clear()
        self._active_trace_id = None

    @property
    def total_spans(self) -> int:
        return len(self._finished)
