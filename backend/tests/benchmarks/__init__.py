"""Benchmark suite for CortexFlow.

Uses pytest-benchmark to measure latency and throughput of critical hot paths:
    - Tool registry: registration, risk scoring, execution pipeline
    - Memory system: short-term read/write, retrieval
    - Model router: provider selection, token budget enforcement

Run with:
    pytest backend/tests/benchmarks/ --benchmark-only
    pytest backend/tests/benchmarks/ --benchmark-only --benchmark-sort=mean

Results are compared against baselines in baseline.json (created on first run).
"""
