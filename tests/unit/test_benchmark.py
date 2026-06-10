"""Unit tests for scripts.benchmark — timing helpers, bench functions, formatting."""

from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable from the project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from benchmark import (
    BenchResult,
    _make_result,
    bench_complexity_detection,
    bench_config_parsing,
    bench_message_splitting,
    format_results_table,
    run_all_benchmarks,
    time_sync,
)

# ---------------------------------------------------------------------------
# _make_result — pure stats helper
# ---------------------------------------------------------------------------


def test_make_result_returns_bench_result():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    r = _make_result("test_bench", 5, samples)
    assert isinstance(r, BenchResult)
    assert r.name == "test_bench"
    assert r.iterations == 5


def test_make_result_mean_correct():
    samples = [10.0, 20.0, 30.0]
    r = _make_result("x", 3, samples)
    assert abs(r.mean_ms - 20.0) < 1e-9


def test_make_result_rate_positive():
    samples = [1.0] * 100
    r = _make_result("x", 100, samples)
    assert r.rate_per_sec > 0


def test_make_result_percentiles_ordered():
    samples = list(range(1, 101))  # 1..100 ms
    r = _make_result("x", 100, samples)
    assert r.p50_ms <= r.p95_ms <= r.p99_ms


def test_bench_result_as_dict_keys():
    r = BenchResult(
        name="foo", iterations=100,
        mean_ms=1.0, p50_ms=0.9, p95_ms=1.5, p99_ms=2.0, rate_per_sec=1000.0,
    )
    d = r.as_dict()
    for key in ("name", "iterations", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "rate_per_sec"):
        assert key in d


# ---------------------------------------------------------------------------
# time_sync
# ---------------------------------------------------------------------------


def test_time_sync_returns_bench_result():
    r = time_sync("noop", lambda: None, n=10)
    assert isinstance(r, BenchResult)
    assert r.name == "noop"
    assert r.iterations == 10


def test_time_sync_mean_positive():
    r = time_sync("noop", lambda: None, n=50)
    assert r.mean_ms >= 0


# ---------------------------------------------------------------------------
# Specific benchmarks (smoke tests — validate they complete and return sane data)
# ---------------------------------------------------------------------------


def test_bench_complexity_detection_runs():
    r = bench_complexity_detection(n=20)
    assert r.name == "complexity_detection"
    assert r.iterations == 20
    assert r.mean_ms >= 0
    assert r.rate_per_sec > 0


def test_bench_message_splitting_runs():
    r = bench_message_splitting(n=20)
    assert r.name == "message_splitting"
    assert r.rate_per_sec > 0


def test_bench_config_parsing_runs():
    r = bench_config_parsing(n=20)
    assert r.name == "config_parsing"
    assert r.rate_per_sec > 0


# ---------------------------------------------------------------------------
# format_results_table
# ---------------------------------------------------------------------------


def test_format_results_table_contains_bench_names():
    results = [
        BenchResult("alpha", 100, 1.0, 0.9, 1.5, 2.0, 1000.0),
        BenchResult("beta", 100, 2.0, 1.8, 2.5, 3.0, 500.0),
    ]
    output = format_results_table(results)
    assert "alpha" in output
    assert "beta" in output


def test_format_results_table_non_empty():
    results = [BenchResult("x", 10, 0.1, 0.09, 0.15, 0.2, 10000.0)]
    assert len(format_results_table(results)) > 0


# ---------------------------------------------------------------------------
# run_all_benchmarks — integration (low iteration count)
# run_all_benchmarks calls asyncio.run() internally, so tests must be sync.
# ---------------------------------------------------------------------------


def test_run_all_benchmarks_returns_list():
    results = run_all_benchmarks(iterations=10)
    assert isinstance(results, list)
    assert len(results) > 0


def test_run_all_benchmarks_include_filter():
    results = run_all_benchmarks(iterations=10, include={"complexity_detection"})
    names = {r.name for r in results}
    assert "complexity_detection" in names
    # Other sync benches should be excluded
    assert "message_splitting" not in names
    assert "config_parsing" not in names
