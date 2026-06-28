"""CortexFlow performance benchmark.

Measures pure-Python hot paths without external services:

    complexity_detection — _detect_complexity() keyword + length heuristic
    message_splitting    — IRCAdapter._split_message() throughput
    config_parsing       — _parse_config() TOML dict → dataclass
    sqlite_memory        — LongTermMemory.store() + search() on :memory:

Usage:
    python scripts/benchmark.py                   # all benchmarks, rich table
    python scripts/benchmark.py --json            # JSON output
    python scripts/benchmark.py --iterations 5000
    python scripts/benchmark.py --bench complexity_detection
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Run via `python scripts/benchmark.py`, Python puts this file's own
# directory (scripts/) on sys.path[0], not the repo root — so the
# `cortexflow_ai` package import below fails unless we add the repo
# root ourselves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class BenchResult:
    name: str
    iterations: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    rate_per_sec: float

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "mean_ms": round(self.mean_ms, 4),
            "p50_ms": round(self.p50_ms, 4),
            "p95_ms": round(self.p95_ms, 4),
            "p99_ms": round(self.p99_ms, 4),
            "rate_per_sec": round(self.rate_per_sec, 1),
        }


# ---------------------------------------------------------------------------
# Core timing helpers
# ---------------------------------------------------------------------------


def time_sync(name: str, fn: Callable, n: int) -> BenchResult:
    """Micro-benchmark a synchronous callable *fn* for *n* iterations."""
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1_000)

    return _make_result(name, n, samples)


async def time_async(name: str, fn: Callable, n: int) -> BenchResult:
    """Micro-benchmark an async callable *fn* for *n* iterations."""
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - t0) * 1_000)

    return _make_result(name, n, samples)


def _make_result(name: str, n: int, samples: list[float]) -> BenchResult:
    sorted_s = sorted(samples)
    mean = statistics.mean(samples)
    idx_p50 = max(0, int(n * 0.50) - 1)
    idx_p95 = max(0, int(n * 0.95) - 1)
    idx_p99 = max(0, int(n * 0.99) - 1)
    return BenchResult(
        name=name,
        iterations=n,
        mean_ms=mean,
        p50_ms=sorted_s[idx_p50],
        p95_ms=sorted_s[idx_p95],
        p99_ms=sorted_s[idx_p99],
        rate_per_sec=(1_000.0 / mean) if mean > 0 else float("inf"),
    )


# ---------------------------------------------------------------------------
# Individual benchmarks
# ---------------------------------------------------------------------------


def bench_complexity_detection(n: int = 2000) -> BenchResult:
    """Benchmark ModelRouter._detect_complexity() across a mixed corpus."""
    from cortexflow_ai.models.router import _detect_complexity

    corpus = [
        "hi",
        "what time is it",
        "analyze the trade-offs of microservices vs monoliths",
        "compare Redis and Memcached for caching",
        " ".join(["word"] * 210),  # long prompt → complex
        "explain how transformers work in detail",
        "set a timer for 5 minutes",
        "research the history of machine learning",
        "thanks",
        "why does garbage collection pause the JVM",
    ]

    idx = 0

    def _fn() -> None:
        nonlocal idx
        _detect_complexity(corpus[idx % len(corpus)])
        idx += 1

    return time_sync("complexity_detection", _fn, n)


def bench_message_splitting(n: int = 2000) -> BenchResult:
    """Benchmark IRCAdapter._split_message() on long payloads."""
    from cortexflow_ai.channels.irc import _split_message

    long_text = "x" * 1200  # 3 chunks of 400

    def _fn() -> None:
        _split_message(long_text, max_len=400)

    return time_sync("message_splitting", _fn, n)


def bench_config_parsing(n: int = 2000) -> BenchResult:
    """Benchmark _parse_config() converting a raw dict to CortexFlowConfig."""
    from cortexflow_ai.config import _parse_config

    raw: dict = {
        "agent": {"name": "BenchBot", "model": "auto"},
        "models": {"primary": "claude-opus-4-8", "fallback": "gemini-2.0-flash"},
        "memory": {"short_term_ttl": 1800, "long_term_days": 60},
        "voice": {"stt": "whisper", "tts": "kokoro"},
        "gateway": {"port": 7432, "bind": "127.0.0.1"},
        "channels": {
            "telegram": {"enabled": True, "bot_token": "ENV:TG_TOKEN"},
            "discord": {"enabled": False},
        },
    }

    def _fn() -> None:
        _parse_config(raw)

    return time_sync("config_parsing", _fn, n)


async def bench_sqlite_memory(n: int = 500) -> BenchResult:
    """Benchmark LongTermMemory.store() + search() on a temp SQLite file."""
    import os
    import tempfile

    from cortexflow_ai.memory.long_term import LongTermMemory

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        lt = LongTermMemory(db_path=db_path)
        await lt.init_schema()

        counter = 0

        async def _fn() -> None:
            nonlocal counter
            await lt.store(
                session_id="bench",
                content=f"benchmark entry {counter}",
                importance=0.5,
                memory_type="fact",
            )
            await lt.search(session_id="bench", query="benchmark", limit=5)
            counter += 1

        return await time_async("sqlite_memory", _fn, n)
    finally:
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_ALL_SYNC_BENCHES: dict[str, Callable[..., BenchResult]] = {
    "complexity_detection": bench_complexity_detection,
    "message_splitting": bench_message_splitting,
    "config_parsing": bench_config_parsing,
}

_ALL_ASYNC_BENCHES: dict[str, Callable[..., object]] = {
    "sqlite_memory": bench_sqlite_memory,
}


def run_all_benchmarks(
    iterations: int = 2000,
    include: set[str] | None = None,
) -> list[BenchResult]:
    """Run all (or a selected subset of) benchmarks and return results."""
    results: list[BenchResult] = []

    for name, fn in _ALL_SYNC_BENCHES.items():
        if include is None or name in include:
            results.append(fn(n=iterations))

    async def _run_async() -> None:
        for name, fn in _ALL_ASYNC_BENCHES.items():
            if include is None or name in include:
                results.append(await fn(n=min(iterations, 500)))

    asyncio.run(_run_async())
    return results


def format_results_table(results: list[BenchResult]) -> str:
    """Return a Rich-formatted table string of benchmark results."""
    try:
        from rich.console import Console
        from rich.table import Table
        import io

        table = Table(title="CortexFlow Benchmark Results", show_lines=True)
        table.add_column("Benchmark", style="bold cyan")
        table.add_column("Iterations", justify="right")
        table.add_column("Mean (ms)", justify="right")
        table.add_column("p50 (ms)", justify="right")
        table.add_column("p95 (ms)", justify="right")
        table.add_column("p99 (ms)", justify="right")
        table.add_column("rate/s", justify="right")

        for r in results:
            table.add_row(
                r.name,
                f"{r.iterations:,}",
                f"{r.mean_ms:.3f}",
                f"{r.p50_ms:.3f}",
                f"{r.p95_ms:.3f}",
                f"{r.p99_ms:.3f}",
                f"{r.rate_per_sec:,.0f}",
            )

        buf = io.StringIO()
        Console(file=buf, force_terminal=False).print(table)
        return buf.getvalue()
    except ImportError:
        lines = ["Benchmark Results"]
        for r in results:
            lines.append(
                f"  {r.name}: mean={r.mean_ms:.3f}ms  p99={r.p99_ms:.3f}ms  rate={r.rate_per_sec:.0f}/s"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    # Rich's table uses box-drawing characters that Windows' default
    # console codepage (cp1252) can't encode — reconfigure stdout to
    # UTF-8 so `print()` doesn't raise UnicodeEncodeError there.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="CortexFlow performance benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--iterations", "-n", type=int, default=2000,
        help="Number of iterations per benchmark (default: 2000)",
    )
    parser.add_argument(
        "--bench", "-b", action="append", dest="benches",
        help="Run only these benchmarks (can be repeated)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    include = set(args.benches) if args.benches else None
    results = run_all_benchmarks(iterations=args.iterations, include=include)

    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=2))
    else:
        print(format_results_table(results))

    sys.exit(0)


if __name__ == "__main__":
    main()
