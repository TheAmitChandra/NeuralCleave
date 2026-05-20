"""Prometheus metrics setup for CortexFlow."""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from app.config import get_settings

# ── HTTP metrics ───────────────────────────────────────────────────────────────
http_requests_total = Counter(
    "cortexflow_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "cortexflow_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── Agent metrics ──────────────────────────────────────────────────────────────
agents_active = Gauge(
    "cortexflow_agents_active_total",
    "Number of currently active agents",
    ["agent_type"],
)

agent_tasks_total = Counter(
    "cortexflow_agent_tasks_total",
    "Total tasks processed by agents",
    ["agent_type", "status"],
)

# ── LLM / token metrics ────────────────────────────────────────────────────────
llm_tokens_used_total = Counter(
    "cortexflow_llm_tokens_used_total",
    "Total LLM tokens consumed",
    ["provider", "model", "task_type"],
)

llm_request_duration_seconds = Histogram(
    "cortexflow_llm_request_duration_seconds",
    "LLM API request latency",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

llm_cost_usd_total = Counter(
    "cortexflow_llm_cost_usd_total",
    "Estimated LLM API cost in USD",
    ["provider", "model"],
)

# ── Workflow metrics ───────────────────────────────────────────────────────────
workflows_total = Counter(
    "cortexflow_workflows_total",
    "Total workflows executed",
    ["status"],
)

workflow_duration_seconds = Histogram(
    "cortexflow_workflow_duration_seconds",
    "Workflow execution duration",
    buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

# ── Memory metrics ─────────────────────────────────────────────────────────────
memory_entries_total = Gauge(
    "cortexflow_memory_entries_total",
    "Total memory entries in store",
    ["tier"],
)

# ── Tool execution metrics ─────────────────────────────────────────────────────
tool_executions_total = Counter(
    "cortexflow_tool_executions_total",
    "Total tool executions",
    ["tool_name", "status", "isolation_level"],
)

tool_risk_score = Histogram(
    "cortexflow_tool_risk_score",
    "Distribution of tool execution risk scores",
    buckets=[10, 25, 50, 60, 75, 86, 100],
)


def setup_metrics() -> None:
    """Start Prometheus metrics HTTP server on configured port."""
    settings = get_settings()
    if settings.APP_ENV not in ("test",):
        start_http_server(settings.PROMETHEUS_PORT)
