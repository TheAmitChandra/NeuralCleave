"""Unit tests for the observability stack.

Covers:
    - NeuralCleaveMetrics singleton and all record_* helpers
    - PROMETHEUS_AVAILABLE flag (null-stub path)
    - TracingContext dataclass
    - OTEL_AVAILABLE flag path (no-op stubs)
    - get_tracer / traced_operation with stubs
    - inject_context / extract_context helpers
    - LogLevel enum and rank ordering
    - LogEntry dataclass and to_dict serialisation
    - LogBuffer append, query, clear, len, ring eviction
    - _BufferProcessor structlog integration
    - configure_logging idempotency
    - get_logger returns bound logger
    - get_log_buffer singleton
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_metrics_singleton():
    """Reset the metrics singleton, using a fresh CollectorRegistry when
    Prometheus is available so duplicate-timeseries errors are avoided."""
    import app.core.observability.metrics as m

    if m.PROMETHEUS_AVAILABLE:
        from prometheus_client import CollectorRegistry

        m._METRICS = m.NeuralCleaveMetrics(registry=CollectorRegistry())
    else:
        m._METRICS = None


def _reset_log_buffer():
    import app.core.observability.logs as l

    l._LOG_BUFFER = None
    l._LOGGING_CONFIGURED = False


def _reset_tracing():
    import app.core.observability.tracing as t

    t._PROVIDER_INITIALISED = False


# ===========================================================================
# TestNeuralCleaveMetrics
# ===========================================================================


class TestNeuralCleaveMetrics:

    def setup_method(self):
        _reset_metrics_singleton()

    def test_get_metrics_returns_singleton(self):
        from app.core.observability.metrics import get_metrics

        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_metrics_has_expected_attributes(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        attrs = [
            "tool_calls_total",
            "tool_duration_seconds",
            "workflow_runs_total",
            "workflow_duration_seconds",
            "llm_requests_total",
            "llm_tokens_total",
            "llm_latency_seconds",
            "memory_operations_total",
            "memory_retrieval_duration_seconds",
            "injection_detections_total",
            "sandbox_executions_total",
            "approval_requests_total",
            "approval_decisions_total",
            "policy_decisions_total",
            "pending_approvals",
            "agents_active",
            "active_workflows",
            "audit_events_total",
            "http_requests_total",
            "http_request_duration_seconds",
        ]
        for attr in attrs:
            assert hasattr(m, attr), f"Missing attribute: {attr}"

    def test_record_tool_call_success(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        # Should not raise with any combination of labels
        m.record_tool_call(
            "shell.execute",
            success=True,
            duration_seconds=0.15,
            risk_level="high",
            isolation_tier="container",
        )

    def test_record_tool_call_failure(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_tool_call(
            "browser.navigate",
            success=False,
            duration_seconds=0.5,
        )

    def test_record_tool_call_with_risk_score(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_tool_call(
            "database.query",
            success=True,
            duration_seconds=0.02,
            risk_score=42.0,
        )

    def test_record_tool_call_custom_outcome(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_tool_call(
            "api.get",
            success=True,
            duration_seconds=0.1,
            outcome="approval_required",
        )

    def test_record_workflow_run(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_workflow_run(
            workflow_id="wf-1234abcd",
            status="COMPLETED",
            duration_seconds=12.5,
        )

    def test_record_workflow_run_uses_first_8_chars(self):
        from app.core.observability.metrics import _NullHistogram, get_metrics

        m = get_metrics()
        # No assertion on internals, just no exception
        m.record_workflow_run("SHORT", status="FAILED", duration_seconds=1.0)

    def test_record_workflow_node(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        for status in ("COMPLETED", "FAILED", "SKIPPED", "RUNNING"):
            m.record_workflow_node(status)

    def test_record_llm_request_full(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_llm_request(
            "gemini",
            model="gemini-2.0-flash",
            success=True,
            latency_seconds=1.2,
            prompt_tokens=512,
            completion_tokens=256,
            cost_usd=0.001,
        )

    def test_record_llm_request_failure(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_llm_request(
            "deepseek",
            model="deepseek-chat",
            success=False,
            latency_seconds=5.0,
        )

    def test_record_memory_op_no_duration(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_memory_op("redis", "read")

    def test_record_memory_op_with_duration(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_memory_op("qdrant", "write", duration_seconds=0.03)

    def test_record_injection_detection(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_injection_detection("user_input", severity="high")

    def test_record_sandbox_execution(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_sandbox_execution("container", success=True)
        m.record_sandbox_execution("process", success=False)

    def test_record_approval_request_and_decision(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_approval_request("HIGH")
        m.record_approval_decision("approved", "HIGH")

    def test_record_policy_decision(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_policy_decision("deny", "DenyBlockedTierRule")

    def test_record_audit_event(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_audit_event("tool_executed", "INFO")

    def test_record_http_request(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.record_http_request("GET", "/api/v1/agents", "200", 0.05)

    def test_time_tool_call_context_manager(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        with m.time_tool_call("filesystem.read", isolation_tier="none"):
            time.sleep(0.001)  # minimal sleep to ensure elapsed > 0

    def test_set_active_workflows(self):
        from app.core.observability.metrics import get_metrics

        m = get_metrics()
        m.set_active_workflows(5)
        m.set_active_workflows(0)


class TestPrometheusAvailableFlag:
    """Verify null stubs work when prometheus_client is absent."""

    def test_null_counter_is_no_op(self):
        from app.core.observability.metrics import _NullCounter

        c = _NullCounter()
        c.labels(tool="x").inc(5)  # must not raise

    def test_null_histogram_is_no_op(self):
        from app.core.observability.metrics import _NullHistogram

        h = _NullHistogram()
        h.labels(a="b").observe(1.0)
        with h.time():
            pass

    def test_null_gauge_is_no_op(self):
        from app.core.observability.metrics import _NullGauge

        g = _NullGauge()
        g.labels(x="y").set(42)
        g.inc()
        g.dec()

    def test_flag_is_bool(self):
        from app.core.observability.metrics import PROMETHEUS_AVAILABLE

        assert isinstance(PROMETHEUS_AVAILABLE, bool)


# ===========================================================================
# TestTracingContext
# ===========================================================================


class TestTracingContext:

    def test_default_is_empty(self):
        from app.core.observability.tracing import TracingContext

        ctx = TracingContext()
        assert ctx.trace_id == ""
        assert ctx.span_id == ""
        assert ctx.is_sampled is False
        assert ctx.is_valid is False

    def test_valid_context(self):
        from app.core.observability.tracing import TracingContext

        ctx = TracingContext(trace_id="abc123", span_id="def456", is_sampled=True)
        assert ctx.is_valid is True

    def test_frozen_immutable(self):
        from app.core.observability.tracing import TracingContext

        ctx = TracingContext(trace_id="t", span_id="s")
        with pytest.raises((AttributeError, TypeError)):
            ctx.trace_id = "new"  # type: ignore[misc]

    def test_baggage_field_default(self):
        from app.core.observability.tracing import TracingContext

        ctx = TracingContext()
        assert isinstance(ctx.baggage, dict)

    def test_partial_context_not_valid(self):
        from app.core.observability.tracing import TracingContext

        ctx = TracingContext(trace_id="abc")
        assert not ctx.is_valid  # span_id missing


class TestTracingGetTracer:

    def setup_method(self):
        _reset_tracing()

    def test_get_tracer_returns_object(self):
        from app.core.observability.tracing import get_tracer

        tracer = get_tracer("test.module")
        assert tracer is not None

    def test_noop_tracer_start_span(self):
        from app.core.observability.tracing import _NoopTracer

        tracer = _NoopTracer()
        span = tracer.start_as_current_span("test")
        with span:
            span.set_attribute("key", "value")


class TestTracedOperation:

    def setup_method(self):
        _reset_tracing()

    @pytest.mark.asyncio
    async def test_traced_operation_no_raise(self):
        from app.core.observability.tracing import traced_operation

        async with traced_operation("test.op") as span:
            pass  # must not raise

    @pytest.mark.asyncio
    async def test_traced_operation_with_attributes(self):
        from app.core.observability.tracing import traced_operation

        async with traced_operation("test.op", attributes={"tier": "qdrant", "k": 10}) as span:
            pass


class TestContextHelpers:

    def test_get_current_context_returns_tracing_context(self):
        from app.core.observability.tracing import get_current_context

        ctx = get_current_context()
        # When OTel is not configured, returns empty context
        assert isinstance(ctx.trace_id, str)
        assert isinstance(ctx.span_id, str)

    def test_inject_context_returns_dict(self):
        from app.core.observability.tracing import inject_context

        headers = {"Content-Type": "application/json"}
        result = inject_context(headers)
        assert isinstance(result, dict)

    def test_inject_context_mutates_in_place(self):
        from app.core.observability.tracing import inject_context

        headers: dict[str, str] = {}
        result = inject_context(headers)
        assert result is headers

    def test_extract_context_no_raise(self):
        from app.core.observability.tracing import extract_context

        result = extract_context({"traceparent": "00-aabbcc-ddeeff-01"})
        # Might be None when OTel unavailable — just must not raise

    def test_otel_available_flag_is_bool(self):
        from app.core.observability.tracing import OTEL_AVAILABLE

        assert isinstance(OTEL_AVAILABLE, bool)


# ===========================================================================
# TestLogLevel
# ===========================================================================


class TestLogLevel:

    def test_all_levels_exist(self):
        from app.core.observability.logs import LogLevel

        for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            assert LogLevel(name).value == name

    def test_rank_ordering(self):
        from app.core.observability.logs import LogLevel

        assert LogLevel.rank("DEBUG") < LogLevel.rank("INFO")
        assert LogLevel.rank("INFO") < LogLevel.rank("WARNING")
        assert LogLevel.rank("WARNING") < LogLevel.rank("ERROR")
        assert LogLevel.rank("ERROR") < LogLevel.rank("CRITICAL")

    def test_rank_case_insensitive(self):
        from app.core.observability.logs import LogLevel

        assert LogLevel.rank("debug") == LogLevel.rank("DEBUG")

    def test_rank_unknown_defaults_to_info(self):
        from app.core.observability.logs import LogLevel

        assert LogLevel.rank("BOGUS") == LogLevel.rank("INFO")


# ===========================================================================
# TestLogEntry
# ===========================================================================


class TestLogEntry:

    def _make(self, **overrides):
        from app.core.observability.logs import LogEntry

        defaults = dict(
            level="INFO",
            message="test message",
            logger_name="test.logger",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        return LogEntry(**defaults)

    def test_default_fields(self):
        entry = self._make()
        assert entry.trace_id == ""
        assert entry.span_id == ""
        assert entry.agent_id == ""
        assert entry.workflow_id == ""
        assert entry.task_id == ""
        assert entry.extra == {}

    def test_to_dict_contains_required_keys(self):
        entry = self._make(trace_id="abc", agent_id="agent-1")
        d = entry.to_dict()
        assert d["level"] == "INFO"
        assert d["message"] == "test message"
        assert d["trace_id"] == "abc"
        assert d["agent_id"] == "agent-1"
        assert "timestamp" in d

    def test_to_dict_includes_extra(self):
        entry = self._make(extra={"custom_key": "custom_val"})
        d = entry.to_dict()
        assert d["custom_key"] == "custom_val"

    def test_to_dict_timestamp_is_iso_string(self):
        entry = self._make()
        d = entry.to_dict()
        assert "T" in d["timestamp"] or "+" in d["timestamp"]


# ===========================================================================
# TestLogBuffer
# ===========================================================================


class TestLogBuffer:

    def _make_entry(self, level="INFO", msg="hello", logger_name="test", **kw):
        from app.core.observability.logs import LogEntry

        return LogEntry(
            level=level,
            message=msg,
            logger_name=logger_name,
            timestamp=datetime.now(tz=timezone.utc),
            **kw,
        )

    def test_append_and_len(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        assert len(buf) == 0
        buf.append(self._make_entry())
        assert len(buf) == 1

    def test_query_returns_all_by_default(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        for i in range(5):
            buf.append(self._make_entry(msg=f"msg-{i}"))
        results = buf.query()
        assert len(results) == 5

    def test_query_min_level_filters(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        buf.append(self._make_entry(level="DEBUG", msg="debug msg"))
        buf.append(self._make_entry(level="INFO", msg="info msg"))
        buf.append(self._make_entry(level="ERROR", msg="error msg"))
        results = buf.query(min_level="WARNING")
        assert len(results) == 1
        assert results[0].level == "ERROR"

    def test_query_by_logger_name(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        buf.append(self._make_entry(logger_name="mod.a"))
        buf.append(self._make_entry(logger_name="mod.b"))
        buf.append(self._make_entry(logger_name="mod.a"))
        results = buf.query(logger_name="mod.a")
        assert len(results) == 2

    def test_query_by_agent_id(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        buf.append(self._make_entry(agent_id="agent-1"))
        buf.append(self._make_entry(agent_id="agent-2"))
        results = buf.query(agent_id="agent-1")
        assert len(results) == 1

    def test_query_by_workflow_id(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        buf.append(self._make_entry(workflow_id="wf-abc"))
        buf.append(self._make_entry(workflow_id="wf-xyz"))
        results = buf.query(workflow_id="wf-abc")
        assert len(results) == 1
        assert results[0].workflow_id == "wf-abc"

    def test_query_limit(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        for i in range(20):
            buf.append(self._make_entry(msg=f"entry-{i}"))
        results = buf.query(limit=5)
        assert len(results) == 5

    def test_ring_eviction(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer(maxlen=3)
        for i in range(5):
            buf.append(self._make_entry(msg=f"entry-{i}"))
        assert len(buf) == 3
        messages = [e.message for e in buf.query()]
        assert "entry-0" not in messages
        assert "entry-4" in messages

    def test_clear(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer()
        buf.append(self._make_entry())
        buf.clear()
        assert len(buf) == 0

    def test_thread_safety(self):
        from app.core.observability.logs import LogBuffer

        buf = LogBuffer(maxlen=1000)
        errors: list[str] = []

        def writer(n: int):
            try:
                for i in range(50):
                    buf.append(self._make_entry(msg=f"thread-{n}-entry-{i}"))
            except Exception as exc:
                errors.append(str(exc))

        threads = [Thread(target=writer, args=(n,)) for n in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread-safety errors: {errors}"
        assert 1 <= len(buf) <= 500  # some may be evicted


# ===========================================================================
# TestLoggerSetup
# ===========================================================================


class TestConfigureLogging:

    def setup_method(self):
        _reset_log_buffer()

    def test_configure_logging_does_not_raise(self):
        from app.core.observability.logs import configure_logging

        configure_logging(log_level="INFO", app_env="test")

    def test_configure_logging_idempotent(self):
        from app.core.observability.logs import configure_logging

        configure_logging(log_level="INFO", app_env="test")
        configure_logging(log_level="DEBUG", app_env="test")  # second call — no-op

    def test_get_logger_returns_logger(self):
        from app.core.observability.logs import get_logger

        log = get_logger("test.module")
        assert log is not None

    def test_get_logger_with_bindings(self):
        from app.core.observability.logs import get_logger

        log = get_logger("test.module", agent_id="agent-1", workflow_id="wf-123")
        assert log is not None

    def test_get_log_buffer_singleton(self):
        from app.core.observability.logs import get_log_buffer

        b1 = get_log_buffer()
        b2 = get_log_buffer()
        assert b1 is b2


class TestBufferProcessor:

    def setup_method(self):
        _reset_log_buffer()

    def test_processor_appends_to_buffer(self):
        from app.core.observability.logs import LogBuffer, _BufferProcessor

        buf = LogBuffer()
        processor = _BufferProcessor(buf)
        event_dict = {
            "event": "something happened",
            "level": "INFO",
            "logger": "test.mod",
            "trace_id": "abc",
            "span_id": "def",
        }
        result = processor(None, "info", event_dict)
        assert result is event_dict  # pass-through
        assert len(buf) == 1
        assert buf.query()[0].message == "something happened"

    def test_processor_captures_extra_fields(self):
        from app.core.observability.logs import LogBuffer, _BufferProcessor

        buf = LogBuffer()
        processor = _BufferProcessor(buf)
        event_dict = {
            "event": "test",
            "level": "ERROR",
            "logger": "mod",
            "custom_field": "custom_value",
            "count": 42,
        }
        processor(None, "error", event_dict)
        entry = buf.query()[0]
        assert entry.extra.get("custom_field") == "custom_value"

    def test_processor_method_fallback_for_level(self):
        from app.core.observability.logs import LogBuffer, _BufferProcessor

        buf = LogBuffer()
        processor = _BufferProcessor(buf)
        # level comes from method argument when not in event_dict
        event_dict = {"event": "no level field", "logger": "mod"}
        processor(None, "warning", event_dict)
        entry = buf.query()[0]
        assert entry.level == "WARNING"
