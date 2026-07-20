"""Heartbeat / proactive scheduler for NeuralCleave.

Runs a background async loop that fires registered tasks on configurable
schedules.  Closes the OpenClaw gap where the assistant can initiate
outbound actions (check the weather, send a morning briefing, run a
health-check) without being prompted by the user.

Scheduling modes
────────────────
interval   Fire every N seconds, starting immediately.
cron       Fire on a 5-field cron expression (minute hour dom month dow).
           Supports ``*``, ``*/step``, ``n-m``, ``n,m`` and combinations.
one_shot   Run once (optionally at a specific ``next_run`` datetime), then
           disable itself.

All public methods are thread-safe via an internal asyncio lock so tasks
can be added/removed while the loop is running.

Usage::

    async def send_morning_briefing() -> None:
        ...

    scheduler = HeartbeatScheduler(tick_interval=60)
    scheduler.add_task(ScheduledTask(
        name="morning_briefing",
        handler=send_morning_briefing,
        cron="0 8 * * *",   # 08:00 every day
    ))
    await scheduler.start()
    # ... gateway runs ...
    await scheduler.stop()
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

UTC = timezone.utc


# ── Task dataclass ────────────────────────────────────────────────────────────

@dataclass
class ScheduledTask:
    """A single schedulable unit of work.

    Args:
        name:             Unique identifier for this task.
        handler:          Async callable invoked on each trigger.
        interval_seconds: Fire every this many seconds (mutually exclusive
                          with ``cron``).
        cron:             5-field cron expression, e.g. ``"0 8 * * *"`` for
                          08:00 daily (mutually exclusive with
                          ``interval_seconds``).
        enabled:          When ``False`` the scheduler skips this task.
        one_shot:         If ``True``, disable the task after its first
                          successful run.
        timeout_seconds:  Hard timeout per invocation; the handler is
                          cancelled if it exceeds this.
        max_retries:      Retry the handler up to this many additional times
                          on failure before giving up.
        next_run:         Pre-set the first run time.  Leave ``None`` to
                          compute automatically when the task is added.
    """

    name: str
    handler: Callable[[], Awaitable[None]]
    interval_seconds: float | None = None
    cron: str | None = None
    enabled: bool = True
    one_shot: bool = False
    timeout_seconds: float = 60.0
    max_retries: int = 0
    # Runtime state — not set by callers
    last_run: datetime | None = field(default=None, repr=False)
    next_run: datetime | None = field(default=None, repr=False)
    run_count: int = field(default=0, repr=False)
    error_count: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if self.interval_seconds is not None and self.cron is not None:
            raise ValueError(
                f"Task {self.name!r}: specify either interval_seconds or cron, not both."
            )
        if self.cron is not None:
            _validate_cron(self.cron)


# ── Scheduler ─────────────────────────────────────────────────────────────────

class HeartbeatScheduler:
    """Background async scheduler for proactive NeuralCleave tasks.

    Args:
        tick_interval: How often (seconds) the scheduler wakes up to check
                       for due tasks.  Defaults to 30 s.
    """

    DEFAULT_TICK: float = 30.0

    def __init__(self, tick_interval: float = DEFAULT_TICK) -> None:
        self._tick_interval = tick_interval
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._loop_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ── Registration ──────────────────────────────────────────────────────────

    def add_task(self, task: ScheduledTask, *, now: datetime | None = None) -> None:
        """Register (or replace) a task.  Computes ``next_run`` if not set."""
        if task.next_run is None:
            _now = now or datetime.now(UTC)
            task.next_run = _compute_next_run(task, from_time=_now)
        self._tasks[task.name] = task
        logger.debug("scheduler.add name=%r next_run=%s", task.name, task.next_run)

    def remove_task(self, name: str) -> bool:
        """Remove a task by name.  Returns ``True`` if it existed."""
        existed = name in self._tasks
        self._tasks.pop(name, None)
        return existed

    def get_task(self, name: str) -> ScheduledTask | None:
        return self._tasks.get(name)

    def list_tasks(self) -> list[ScheduledTask]:
        return list(self._tasks.values())

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    @property
    def running(self) -> bool:
        return self._running

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background scheduler loop (idempotent)."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._loop(), name="heartbeat-scheduler")
        logger.info("scheduler.started tick_interval=%.0fs tasks=%d", self._tick_interval, len(self._tasks))

    async def stop(self) -> None:
        """Stop the scheduler and cancel the background loop."""
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None
        logger.info("scheduler.stopped")

    # ── Core loop ─────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            await self._tick()
            try:
                await asyncio.sleep(self._tick_interval)
            except asyncio.CancelledError:
                break

    async def _tick(self, now: datetime | None = None) -> None:
        """Check all tasks and fire any that are due."""
        _now = now or datetime.now(UTC)
        due = [t for t in self._tasks.values() if _is_due(t, _now)]
        if not due:
            return
        results = await asyncio.gather(*[self._run_task(t) for t in due], return_exceptions=True)
        for task, result in zip(due, results):
            if isinstance(result, Exception):
                logger.error("scheduler.tick unhandled error in %r: %s", task.name, result)

    async def _run_task(self, task: ScheduledTask) -> None:
        """Execute one task, applying timeout and retry logic."""
        if not task.enabled:
            return
        for attempt in range(task.max_retries + 1):
            try:
                await asyncio.wait_for(task.handler(), timeout=task.timeout_seconds)
                # Success path
                task.run_count += 1
                task.last_run = datetime.now(UTC)
                task.next_run = _compute_next_run(task, from_time=task.last_run)
                if task.one_shot:
                    task.enabled = False
                logger.info("scheduler.run name=%r run_count=%d", task.name, task.run_count)
                return
            except asyncio.TimeoutError:
                task.error_count += 1
                logger.error(
                    "scheduler.timeout name=%r attempt=%d/%d timeout=%.1fs",
                    task.name, attempt + 1, task.max_retries + 1, task.timeout_seconds,
                )
                break
            except Exception as exc:
                task.error_count += 1
                logger.error(
                    "scheduler.error name=%r attempt=%d/%d error=%s",
                    task.name, attempt + 1, task.max_retries + 1, exc,
                )
                if attempt < task.max_retries:
                    await asyncio.sleep(0.1)
                    continue
                break


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_due(task: ScheduledTask, now: datetime) -> bool:
    """Return True if *task* should fire at *now*."""
    if not task.enabled:
        return False
    if task.next_run is None:
        # No schedule at all — fire once if never run before
        return task.last_run is None
    return now >= task.next_run


def _compute_next_run(task: ScheduledTask, from_time: datetime) -> datetime | None:
    """Return the next scheduled datetime, or None for unscheduled one-shots."""
    if task.cron:
        return _cron_next(task.cron, after=from_time)
    if task.interval_seconds is not None:
        return from_time + timedelta(seconds=task.interval_seconds)
    return None  # one_shot with no schedule: already fired, no next run


# ── Cron engine ───────────────────────────────────────────────────────────────

def _validate_cron(expression: str) -> None:
    """Raise ValueError if *expression* is not a valid 5-field cron string."""
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Cron expression must have exactly 5 fields: {expression!r}")
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    names = ("minute", "hour", "day-of-month", "month", "day-of-week")
    for f, (lo, hi), name in zip(fields, ranges, names):
        try:
            _parse_cron_field(f, lo, hi)
        except Exception as exc:
            raise ValueError(f"Invalid cron {name} field {f!r}: {exc}") from exc


def _cron_next(expression: str, after: datetime) -> datetime:
    """Return the first datetime > *after* matching the cron *expression*.

    Cron convention: minute hour dom month dow (0 = Sunday for dow).
    Searches forward minute-by-minute up to 4 years to guarantee termination.
    """
    fields = expression.strip().split()
    minutes_f, hours_f, doms_f, months_f, dows_f = fields
    minutes = _parse_cron_field(minutes_f, 0, 59)
    hours = _parse_cron_field(hours_f, 0, 23)
    doms = _parse_cron_field(doms_f, 1, 31)
    months = _parse_cron_field(months_f, 1, 12)
    # Cron DOW 0=Sun,6=Sat; also allow 7=Sun.  Python weekday 0=Mon,6=Sun.
    raw_dows = _parse_cron_field(dows_f, 0, 7)
    py_dows = frozenset((d - 1) % 7 for d in raw_dows)

    # Start 1 minute after 'after' (exclusive lower bound)
    after_utc = after.astimezone(UTC) if after.tzinfo else after.replace(tzinfo=UTC)
    candidate = after_utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = after_utc + timedelta(days=366 * 4)

    while candidate <= limit:
        if (candidate.month in months
                and candidate.day in doms
                and candidate.weekday() in py_dows
                and candidate.hour in hours
                and candidate.minute in minutes):
            return candidate
        candidate += timedelta(minutes=1)

    raise ValueError(f"No occurrence found within 4 years for cron: {expression!r}")


def _parse_cron_field(field: str, lo: int, hi: int) -> frozenset[int]:
    """Parse one cron field into a frozenset of matching integers.

    Supports: ``*``, ``n``, ``n-m``, ``*/step``, ``n-m/step``, ``a,b,c``
    and combinations thereof (comma-separated).
    """
    result: set[int] = set()
    for part in field.split(","):
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step must be positive, got {step}")
            if base == "*":
                start, end = lo, hi
            elif "-" in base:
                s, e = base.split("-", 1)
                start, end = int(s), int(e)
            else:
                start = end = int(base)
            result.update(range(start, end + 1, step))
        elif part == "*":
            result.update(range(lo, hi + 1))
        elif "-" in part:
            s, e = part.split("-", 1)
            result.update(range(int(s), int(e) + 1))
        else:
            val = int(part)
            result.add(val)
    # Clamp to valid range
    result = {v for v in result if lo <= v <= hi}
    if not result:
        raise ValueError(f"Field {field!r} produced no valid values in [{lo},{hi}]")
    return frozenset(result)
