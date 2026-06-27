"""Unit tests for cortexflow.observability.metrics — Counter, Gauge, Histogram, MetricsRegistry."""

from __future__ import annotations

from cortexflow_ai.observability.metrics import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    _fmt_labels,
    _label_key,
)

# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


def test_counter_starts_at_zero():
    c = Counter(name="test", description="desc")
    assert c.get() == 0.0


def test_counter_inc_default_amount():
    c = Counter(name="c", description="d")
    c.inc()
    assert c.get() == 1.0


def test_counter_inc_custom_amount():
    c = Counter(name="c", description="d")
    c.inc(5.0)
    assert c.get() == 5.0


def test_counter_inc_with_labels():
    c = Counter(name="c", description="d")
    c.inc(labels={"channel": "telegram"})
    c.inc(labels={"channel": "telegram"})
    c.inc(labels={"channel": "discord"})
    assert c.get(labels={"channel": "telegram"}) == 2.0
    assert c.get(labels={"channel": "discord"}) == 1.0


def test_counter_snapshot_returns_dict():
    c = Counter(name="c", description="d")
    c.inc(3.0)
    snap = c.snapshot()
    assert isinstance(snap, dict)
    assert snap[""] == 3.0


def test_counter_reset():
    c = Counter(name="c", description="d")
    c.inc(10.0)
    c.reset()
    assert c.get() == 0.0


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------


def test_gauge_set():
    g = Gauge(name="g", description="d")
    g.set(42.0)
    assert g.get() == 42.0


def test_gauge_inc_dec():
    g = Gauge(name="g", description="d")
    g.inc(3.0)
    g.dec(1.0)
    assert g.get() == 2.0


def test_gauge_with_labels():
    g = Gauge(name="g", description="d")
    g.set(1.0, labels={"channel": "teams"})
    g.set(0.0, labels={"channel": "slack"})
    assert g.get(labels={"channel": "teams"}) == 1.0
    assert g.get(labels={"channel": "slack"}) == 0.0


def test_gauge_snapshot():
    g = Gauge(name="g", description="d")
    g.set(7.0)
    assert g.snapshot()[""] == 7.0


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


def test_histogram_observe_increments_count():
    h = Histogram(name="h", description="d", buckets=(100, 500, float("inf")))
    h.observe(200.0)
    assert h.get_count() == 1


def test_histogram_observe_increments_sum():
    h = Histogram(name="h", description="d", buckets=(100, 500, float("inf")))
    h.observe(200.0)
    assert h.get_sum() == 200.0


def test_histogram_bucket_accumulation():
    h = Histogram(name="h", description="d", buckets=(100, 500, float("inf")))
    h.observe(50.0)
    h.observe(300.0)
    buckets = h.get_buckets()
    # ≤100: 1 observation (50), ≤500: 2 (50+300), +Inf: 2
    assert buckets[0][1] == 1
    assert buckets[1][1] == 2
    assert buckets[2][1] == 2


def test_histogram_snapshot_structure():
    h = Histogram(name="h", description="d")
    h.observe(500.0)
    snap = h.snapshot()
    assert "" in snap
    assert "sum" in snap[""]
    assert "count" in snap[""]
    assert "buckets" in snap[""]


# ---------------------------------------------------------------------------
# MetricsRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get():
    r = MetricsRegistry()
    r.register(Counter, "my_counter", "a counter")
    assert r.get("my_counter") is not None


def test_registry_inc_counter():
    r = MetricsRegistry()
    r.register(Counter, "req", "requests")
    r.inc("req", 2.0)
    m = r.get("req")
    assert m.get() == 2.0


def test_registry_set_gauge():
    r = MetricsRegistry()
    r.register(Gauge, "sessions", "active")
    r.set("sessions", 5.0)
    assert r.get("sessions").get() == 5.0


def test_registry_dec_gauge():
    r = MetricsRegistry()
    r.register(Gauge, "sessions", "active")
    r.set("sessions", 5.0)
    r.dec("sessions", 2.0)
    assert r.get("sessions").get() == 3.0


def test_registry_dec_on_non_gauge_is_noop():
    r = MetricsRegistry()
    r.register(Counter, "req", "requests")
    r.dec("req", 1.0)  # must not raise, must not affect the counter
    assert r.get("req").get() == 0.0


def test_registry_observe_histogram():
    r = MetricsRegistry()
    r.register(Histogram, "latency", "ms")
    r.observe("latency", 250.0)
    assert r.get("latency").get_count() == 1


def test_registry_registered_names_sorted():
    r = MetricsRegistry()
    r.register(Counter, "z_metric", "z")
    r.register(Counter, "a_metric", "a")
    names = r.registered_names()
    assert names == sorted(names)


def test_registry_snapshot_includes_all():
    r = MetricsRegistry()
    r.register(Counter, "c1", "counter 1")
    r.register(Gauge, "g1", "gauge 1")
    snap = r.snapshot()
    assert "c1" in snap
    assert "g1" in snap
    assert snap["c1"]["type"] == "counter"
    assert snap["g1"]["type"] == "gauge"


# ---------------------------------------------------------------------------
# Prometheus export
# ---------------------------------------------------------------------------


def test_export_prometheus_counter():
    r = MetricsRegistry()
    r.register(Counter, "msgs", "messages")
    r.inc("msgs", 3.0, labels={"channel": "telegram"})
    output = r.export_prometheus()
    assert "# HELP msgs" in output
    assert "# TYPE msgs counter" in output
    assert 'channel="telegram"' in output


def test_export_prometheus_gauge():
    r = MetricsRegistry()
    r.register(Gauge, "active", "sessions")
    r.set("active", 7.0)
    output = r.export_prometheus()
    assert "# TYPE active gauge" in output
    assert "active{" in output or "active " in output


def test_export_prometheus_histogram():
    r = MetricsRegistry()
    r.register(Histogram, "lat", "latency", buckets=(100, 500, float("inf")))
    r.observe("lat", 200.0)
    output = r.export_prometheus()
    assert "lat_bucket" in output
    assert "lat_sum" in output
    assert "lat_count" in output
    assert '+Inf' in output


# ---------------------------------------------------------------------------
# Module-level REGISTRY has pre-built metrics
# ---------------------------------------------------------------------------


def test_registry_has_messages_total():
    assert REGISTRY.get("messages_total") is not None


def test_registry_has_generation_latency():
    assert REGISTRY.get("generation_latency_ms") is not None


def test_registry_has_active_sessions():
    assert REGISTRY.get("active_sessions") is not None


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------


def test_label_key_empty():
    assert _label_key(None) == ""
    assert _label_key({}) == ""


def test_label_key_single():
    assert _label_key({"channel": "slack"}) == "channel=slack"


def test_fmt_labels_empty():
    assert _fmt_labels("") == ""


def test_fmt_labels_single():
    result = _fmt_labels("channel=telegram")
    assert result == '{channel="telegram"}'
