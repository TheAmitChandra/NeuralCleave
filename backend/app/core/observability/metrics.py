"""Prometheus Metrics — CortexFlow runtime observability.

Exposes a ``CortexFlowMetrics`` singleton that tracks all runtime
counters, histograms, and gauges for the platform.

Metric categories
─────────────────
    Tool execution   — call counts, durations, success/failure
    Workflow         — run counts, durations, state transitions
    LLM inference    — request counts, token usage, latency
    Memory           — operation counts per tier
    Security         — injection detections, approval requests, sandbox events
    Agent            — active agents, lifecycle transitions
    Governance       — approval decisions, policy denials
    HTTP             — request counts, latencies (from original stub)

Prometheus client availability is guarded so the module imports cleanly
even without ``prometheus-client`` installed.

Usage::

    metrics = get_metrics()
    metrics.record_tool_call(tool_name="shell.execute", success=True, duration=0.42)
    metrics.record_llm_request(provider="gemini", model="gemini-2.0-flash",
                               success=True, latency_seconds=1.2)
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy Prometheus import
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    PROMETHEUS_AVAILABLE = False
    Counter = Gauge = Histogram = start_http_server = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Null metric stubs (used when Prometheus not available)
# ---------------------------------------------------------------------------

class _NullCounter:
    def labels(self, **_: Any) -> "_NullCounter": return self
    def inc(self, amount: float = 1) -> None: pass


class _NullHistogram:
    def labels(self, **_: Any) -> "_NullHistogram": return self
    def observe(self, value: float) -> None: pass

    @contextmanager
    def time(self) -> Generator[None, None, None]:
        yield


class _NullGauge:
    def labels(self, **_: Any) -> "_NullGauge": return self
    def inc(self, amount: float = 1) -> None: pass
    def dec(self, amount: float = 1) -> None: pass
    def set(self, value: float) -> None: pass


# ---------------------------------------------------------------------------
# Metric factory helpers
# ---------------------------------------------------------------------------

_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)


def _counter(name: str, description: str, labels: list[str], registry: Any = None) -> Any:
    if PROMETHEUS_AVAILABLE:
        kw: dict[str, Any] = {"registry": registry} if registry is not None else {}
        return Counter(name, description, labels, **kw)
    return _NullCounter()


def _histogram(
    name: str,
    description: str,
    labels: list[str],
    buckets: tuple = _DURATION_BUCKETS,
    registry: Any = None,
) -> Any:
    if PROMETHEUS_AVAILABLE:
        kw: dict[str, Any] = {"registry": registry} if registry is not None else {}
        return Histogram(name, description, labels, buckets=buckets, **kw)
    return _NullHistogram()


def _gauge(name: str, description: str, labels: list[str], registry: Any = None) -> Any:
    if PROMETHEUS_AVAILABLE:
        kw: dict[str, Any] = {"registry": registry} if registry is not None else {}
        return Gauge(name, description, labels, **kw)
    return _NullGauge()


# ---------------------------------------------------------------------------
# Metrics singleton
# ---------------------------------------------------------------------------

class CortexFlowMetrics:
    """All CortexFlow Prometheus metrics in one registry object.

    Prefer the ``record_*`` helper methods over accessing raw metrics directly.

    Parameters
    ----------
    registry:
        Prometheus ``CollectorRegistry`` to register metrics into.  Pass a
        fresh ``CollectorRegistry()`` in tests to avoid duplicate-timeseries
        errors when the singleton is reset between test cases.  ``None`` (the
        default) uses the global Prometheus registry.
    """

    def __init__(self, registry: Any = None) -> None:
        r = registry  # shorthand passed through every factory call
        # ── HTTP metrics (retained from original stub) ─────────────────────
        self.http_requests_total = _counter(
            "cortexflow_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=r,
        )
        self.http_request_duration_seconds = _histogram(
            "cortexflow_http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint"],
            registry=r,
        )

        # ── Tool metrics ───────────────────────────────────────────────────
        self.tool_calls_total = _counter(
            "cortexflow_tool_calls_total",
            "Total tool invocations by name, risk_level, and outcome",
            ["tool_name", "risk_level", "outcome"],
            registry=r,
        )
        self.tool_duration_seconds = _histogram(
            "cortexflow_tool_duration_seconds",
            "Tool execution wall-clock time",
            ["tool_name", "isolation_tier"],
            registry=r,
        )
        self.tool_risk_score = _histogram(
            "cortexflow_tool_risk_score",
            "Distribution of tool execution risk scores",
            [],
            buckets=(10, 25, 50, 60, 75, 86, 100),
            registry=r,
        )

        # ── Workflow metrics ───────────────────────────────────────────────
        self.workflow_runs_total = _counter(
            "cortexflow_workflow_runs_total",
            "Total workflow run attempts by terminal status",
            ["status"],
            registry=r,
        )
        self.workflow_duration_seconds = _histogram(
            "cortexflow_workflow_duration_seconds",
            "End-to-end workflow execution time",
            ["workflow_id_prefix"],
            buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0),
            registry=r,
        )
        self.workflow_node_executions_total = _counter(
            "cortexflow_workflow_node_executions_total",
            "DAG node executions by status",
            ["node_status"],
            registry=r,
        )

        # ── LLM metrics ───────────────────────────────────────────────────
        self.llm_requests_total = _counter(
            "cortexflow_llm_requests_total",
            "LLM inference calls by provider and outcome",
            ["provider", "model", "outcome"],
            registry=r,
        )
        self.llm_tokens_total = _counter(
            "cortexflow_llm_tokens_total",
            "Total LLM tokens consumed (prompt + completion)",
            ["provider", "model", "token_type"],
            registry=r,
        )
        self.llm_latency_seconds = _histogram(
            "cortexflow_llm_latency_seconds",
            "LLM response latency",
            ["provider", "model"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
            registry=r,
        )
        self.llm_cost_usd_total = _counter(
            "cortexflow_llm_cost_usd_total",
            "Estimated LLM API cost in USD",
            ["provider", "model"],
            registry=r,
        )

        # ── Memory metrics ────────────────────────────────────────────────
        self.memory_operations_total = _counter(
            "cortexflow_memory_operations_total",
            "Memory tier operations by tier and operation type",
            ["tier", "operation"],
            registry=r,
        )
        self.memory_retrieval_duration_seconds = _histogram(
            "cortexflow_memory_retrieval_duration_seconds",
            "Memory retrieval latency by tier",
            ["tier"],
            registry=r,
        )
        self.memory_entries_total = _gauge(
            "cortexflow_memory_entries_total",
            "Total memory entries in store",
            ["tier"],
            registry=r,
        )

        # ── Security / sandbox metrics ────────────────────────────────────
        self.injection_detections_total = _counter(
            "cortexflow_injection_detections_total",
            "Prompt injection detections by source",
            ["source", "severity"],
            registry=r,
        )
        self.sandbox_executions_total = _counter(
            "cortexflow_sandbox_executions_total",
            "Sandbox execution attempts by isolation tier and outcome",
            ["isolation_tier", "outcome"],
            registry=r,
        )

        # ── Approval / governance metrics ─────────────────────────────────
        self.approval_requests_total = _counter(
            "cortexflow_approval_requests_total",
            "Approval requests created by priority",
            ["priority"],
            registry=r,
        )
        self.approval_decisions_total = _counter(
            "cortexflow_approval_decisions_total",
            "Approval decisions by outcome",
            ["decision"],
            registry=r,
        )
        self.policy_decisions_total = _counter(
            "cortexflow_policy_decisions_total",
            "Policy engine decisions by action and rule",
            ["action", "rule_name"],
            registry=r,
        )
        self.pending_approvals = _gauge(
            "cortexflow_pending_approvals",
            "Number of approval requests awaiting decision",
            ["priority"],
            registry=r,
        )

        # ── Agent gauges ──────────────────────────────────────────────────
        self.agents_active = _gauge(
            "cortexflow_agents_active_total",
            "Number of currently active agents",
            ["agent_type"],
            registry=r,
        )
        self.active_workflows = _gauge(
            "cortexflow_active_workflows",
            "Number of currently running workflows",
            [],
            registry=r,
        )
        self.agent_tasks_total = _counter(
            "cortexflow_agent_tasks_total",
            "Total tasks processed by agents",
            ["agent_type", "status"],
            registry=r,
        )

        # ── Audit metrics ─────────────────────────────────────────────────
        self.audit_events_total = _counter(
            "cortexflow_audit_events_total",
            "Audit events by type and severity",
            ["event_type", "severity"],
            registry=r,
        )

    # ------------------------------------------------------------------
    # High-level helper methods
    # ------------------------------------------------------------------

    def record_tool_call(
        self,
        tool_name: str,
        *,
        success: bool,
        duration_seconds: float,
        risk_level: str = "low",
        isolation_tier: str = "process",
        risk_score: float | None = None,
        outcome: str | None = None,
    ) -> None:
        _outcome = outcome or ("success" if success else "error")
        self.tool_calls_total.labels(
            tool_name=tool_name, risk_level=risk_level, outcome=_outcome
        ).inc()
        self.tool_duration_seconds.labels(
            tool_name=tool_name, isolation_tier=isolation_tier
        ).observe(duration_seconds)
        if risk_score is not None:
            self.tool_risk_score.observe(risk_score)

    def record_workflow_run(
        self,
        workflow_id: str,
        *,
        status: str,
        duration_seconds: float,
    ) -> None:
        self.workflow_runs_total.labels(status=status).inc()
        self.workflow_duration_seconds.labels(
            workflow_id_prefix=workflow_id[:8]
        ).observe(duration_seconds)

    def record_workflow_node(self, node_status: str) -> None:
        self.workflow_node_executions_total.labels(node_status=node_status).inc()

    def record_llm_request(
        self,
        provider: str,
        *,
        model: str,
        success: bool,
        latency_seconds: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        outcome = "success" if success else "error"
        self.llm_requests_total.labels(provider=provider, model=model, outcome=outcome).inc()
        self.llm_latency_seconds.labels(provider=provider, model=model).observe(latency_seconds)
        if prompt_tokens:
            self.llm_tokens_total.labels(
                provider=provider, model=model, token_type="prompt"
            ).inc(prompt_tokens)
        if completion_tokens:
            self.llm_tokens_total.labels(
                provider=provider, model=model, token_type="completion"
            ).inc(completion_tokens)
        if cost_usd > 0:
            self.llm_cost_usd_total.labels(provider=provider, model=model).inc(cost_usd)

    def record_memory_op(
        self, tier: str, operation: str, duration_seconds: float = 0.0
    ) -> None:
        self.memory_operations_total.labels(tier=tier, operation=operation).inc()
        if duration_seconds > 0:
            self.memory_retrieval_duration_seconds.labels(tier=tier).observe(duration_seconds)

    def record_injection_detection(self, source: str, severity: str = "medium") -> None:
        self.injection_detections_total.labels(source=source, severity=severity).inc()

    def record_sandbox_execution(self, isolation_tier: str, success: bool) -> None:
        outcome = "success" if success else "error"
        self.sandbox_executions_total.labels(
            isolation_tier=isolation_tier, outcome=outcome
        ).inc()

    def record_approval_request(self, priority: str) -> None:
        self.approval_requests_total.labels(priority=priority).inc()
        self.pending_approvals.labels(priority=priority).inc()

    def record_approval_decision(self, decision: str, priority: str) -> None:
        self.approval_decisions_total.labels(decision=decision).inc()
        self.pending_approvals.labels(priority=priority).dec()

    def record_policy_decision(self, action: str, rule_name: str) -> None:
        self.policy_decisions_total.labels(action=action, rule_name=rule_name).inc()

    def record_audit_event(self, event_type: str, severity: str) -> None:
        self.audit_events_total.labels(event_type=event_type, severity=severity).inc()

    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        self.http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
        self.http_request_duration_seconds.labels(
            method=method, endpoint=endpoint
        ).observe(duration_seconds)

    def set_active_workflows(self, count: int) -> None:
        """Set the gauge tracking currently running workflows."""
        self.active_workflows.set(count)

    @contextmanager
    def time_tool_call(
        self, tool_name: str, *, isolation_tier: str = "process"
    ) -> Generator[None, None, None]:
        """Context manager that records tool duration on exit."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.tool_duration_seconds.labels(
                tool_name=tool_name, isolation_tier=isolation_tier
            ).observe(elapsed)


# ---------------------------------------------------------------------------
# Module-level singleton + setup
# ---------------------------------------------------------------------------

_METRICS: CortexFlowMetrics | None = None


def get_metrics() -> CortexFlowMetrics:
    """Return the process-level metrics singleton (lazy init)."""
    global _METRICS
    if _METRICS is None:
        _METRICS = CortexFlowMetrics()
        logger.info("metrics.initialised", prometheus_available=PROMETHEUS_AVAILABLE)
    return _METRICS


def setup_metrics(port: int = 9090) -> None:
    """Start Prometheus metrics HTTP server (no-op in test / when unavailable)."""
    if not PROMETHEUS_AVAILABLE:
        logger.warning("metrics.prometheus_unavailable")
        return
    try:
        from app.config import get_settings
        settings = get_settings()
        if settings.APP_ENV not in ("test",):
            start_http_server(getattr(settings, "PROMETHEUS_PORT", port))
            logger.info("metrics.http_server_started", port=port)
    except Exception:
        logger.exception("metrics.http_server_failed")
