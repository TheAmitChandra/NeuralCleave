"""Comprehensive tests for cortexflow_ai.scheduler — HeartbeatScheduler.

Test categories
───────────────
 1.  ScheduledTask dataclass                       (tests  1– 9)
 2.  _parse_cron_field                             (tests 10–20)
 3.  _validate_cron                                (tests 21–25)
 4.  _cron_next — basic expressions                (tests 26–38)
 5.  _cron_next — edge cases                       (tests 39–44)
 6.  _compute_next_run                             (tests 45–50)
 7.  _is_due                                       (tests 51–57)
 8.  HeartbeatScheduler — registration             (tests 58–65)
 9.  HeartbeatScheduler — _tick execution          (tests 66–79)
10.  HeartbeatScheduler — timeout & retries        (tests 80–87)
11.  HeartbeatScheduler — one_shot                 (tests 88–92)
12.  HeartbeatScheduler — lifecycle (start/stop)   (tests 93–99)
13.  Gateway integration                           (tests 100–103)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from cortexflow_ai.scheduler import (
    UTC,
    HeartbeatScheduler,
    ScheduledTask,
    _compute_next_run,
    _cron_next,
    _is_due,
    _parse_cron_field,
    _validate_cron,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _dt(year=2025, month=1, day=1, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _interval_task(name="t", seconds=60.0, handler=None) -> ScheduledTask:
    return ScheduledTask(
        name=name,
        handler=handler or AsyncMock(),
        interval_seconds=seconds,
    )


def _cron_task(name="t", cron="* * * * *", handler=None) -> ScheduledTask:
    return ScheduledTask(
        name=name,
        handler=handler or AsyncMock(),
        cron=cron,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. ScheduledTask dataclass
# ─────────────────────────────────────────────────────────────────────────────

def test_task_name_stored() -> None:
    t = _interval_task(name="my_task")
    assert t.name == "my_task"


def test_task_defaults() -> None:
    t = _interval_task()
    assert t.enabled is True
    assert t.one_shot is False
    assert t.max_retries == 0
    assert t.timeout_seconds == 60.0
    assert t.last_run is None
    assert t.next_run is None
    assert t.run_count == 0
    assert t.error_count == 0


def test_task_interval_and_cron_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="not both"):
        ScheduledTask(name="x", handler=AsyncMock(), interval_seconds=60, cron="* * * * *")


def test_task_cron_validated_on_construction() -> None:
    with pytest.raises(ValueError):
        ScheduledTask(name="x", handler=AsyncMock(), cron="bad cron expression")


def test_task_neither_interval_nor_cron_is_valid() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True)
    assert t.interval_seconds is None
    assert t.cron is None


def test_task_enabled_false() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), interval_seconds=10, enabled=False)
    assert not t.enabled


def test_task_custom_timeout() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), interval_seconds=10, timeout_seconds=5.0)
    assert t.timeout_seconds == 5.0


def test_task_custom_max_retries() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), interval_seconds=10, max_retries=3)
    assert t.max_retries == 3


def test_task_one_shot_flag() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True)
    assert t.one_shot is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. _parse_cron_field
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_star_returns_all() -> None:
    assert _parse_cron_field("*", 0, 5) == frozenset({0, 1, 2, 3, 4, 5})


def test_parse_literal_value() -> None:
    assert _parse_cron_field("3", 0, 59) == frozenset({3})


def test_parse_range() -> None:
    assert _parse_cron_field("2-5", 0, 59) == frozenset({2, 3, 4, 5})


def test_parse_star_step() -> None:
    assert _parse_cron_field("*/15", 0, 59) == frozenset({0, 15, 30, 45})


def test_parse_range_step() -> None:
    assert _parse_cron_field("0-30/10", 0, 59) == frozenset({0, 10, 20, 30})


def test_parse_comma_list() -> None:
    assert _parse_cron_field("1,3,5", 0, 59) == frozenset({1, 3, 5})


def test_parse_comma_mixed() -> None:
    result = _parse_cron_field("0,*/30", 0, 59)
    assert 0 in result and 30 in result


def test_parse_clamps_to_range() -> None:
    result = _parse_cron_field("0-10", 5, 59)
    assert all(v >= 5 for v in result)


def test_parse_step_zero_raises() -> None:
    with pytest.raises(ValueError):
        _parse_cron_field("*/0", 0, 59)


def test_parse_out_of_range_only_raises() -> None:
    with pytest.raises(ValueError):
        _parse_cron_field("100", 0, 59)


def test_parse_minute_full_range() -> None:
    result = _parse_cron_field("*", 0, 59)
    assert len(result) == 60


# ─────────────────────────────────────────────────────────────────────────────
# 3. _validate_cron
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_valid_expression() -> None:
    _validate_cron("0 8 * * *")  # must not raise


def test_validate_every_minute() -> None:
    _validate_cron("* * * * *")


def test_validate_too_few_fields_raises() -> None:
    with pytest.raises(ValueError, match="5 fields"):
        _validate_cron("0 8 * *")


def test_validate_too_many_fields_raises() -> None:
    with pytest.raises(ValueError, match="5 fields"):
        _validate_cron("0 8 * * * *")


def test_validate_bad_minute_raises() -> None:
    with pytest.raises(ValueError):
        _validate_cron("60 * * * *")


# ─────────────────────────────────────────────────────────────────────────────
# 4. _cron_next — basic expressions
# ─────────────────────────────────────────────────────────────────────────────

def test_cron_every_minute_advances_one_minute() -> None:
    after = _dt(2025, 1, 1, 12, 0)
    nxt = _cron_next("* * * * *", after)
    assert nxt == _dt(2025, 1, 1, 12, 1)


def test_cron_every_minute_is_always_next_minute() -> None:
    after = _dt(2025, 6, 15, 9, 30)
    nxt = _cron_next("* * * * *", after)
    assert nxt == _dt(2025, 6, 15, 9, 31)


def test_cron_top_of_hour() -> None:
    after = _dt(2025, 1, 1, 12, 0)
    nxt = _cron_next("0 * * * *", after)
    assert nxt == _dt(2025, 1, 1, 13, 0)


def test_cron_specific_time_today() -> None:
    after = _dt(2025, 1, 1, 7, 59)
    nxt = _cron_next("0 8 * * *", after)
    assert nxt == _dt(2025, 1, 1, 8, 0)


def test_cron_specific_time_tomorrow_if_passed() -> None:
    after = _dt(2025, 1, 1, 8, 1)
    nxt = _cron_next("0 8 * * *", after)
    assert nxt == _dt(2025, 1, 2, 8, 0)


def test_cron_step_minutes() -> None:
    after = _dt(2025, 1, 1, 0, 0)
    nxt = _cron_next("*/30 * * * *", after)
    assert nxt == _dt(2025, 1, 1, 0, 30)


def test_cron_step_hours() -> None:
    after = _dt(2025, 1, 1, 0, 0)
    nxt = _cron_next("0 */6 * * *", after)
    assert nxt == _dt(2025, 1, 1, 6, 0)


def test_cron_day_of_month() -> None:
    after = _dt(2025, 1, 1, 0, 0)
    nxt = _cron_next("0 9 15 * *", after)
    assert nxt == _dt(2025, 1, 15, 9, 0)


def test_cron_specific_month() -> None:
    after = _dt(2025, 1, 1, 0, 0)
    nxt = _cron_next("0 0 1 6 *", after)
    assert nxt == _dt(2025, 6, 1, 0, 0)


def test_cron_result_is_always_after_input() -> None:
    after = _dt(2025, 3, 15, 10, 30)
    nxt = _cron_next("* * * * *", after)
    assert nxt > after


def test_cron_result_tz_is_utc() -> None:
    after = _dt(2025, 1, 1, 0, 0)
    nxt = _cron_next("* * * * *", after)
    assert nxt.tzinfo == UTC


def test_cron_second_is_zero() -> None:
    nxt = _cron_next("* * * * *", _dt())
    assert nxt.second == 0


def test_cron_microsecond_is_zero() -> None:
    nxt = _cron_next("* * * * *", _dt())
    assert nxt.microsecond == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. _cron_next — edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_cron_range_in_minute() -> None:
    after = _dt(2025, 1, 1, 12, 0)
    nxt = _cron_next("10-20 12 * * *", after)
    assert nxt == _dt(2025, 1, 1, 12, 10)


def test_cron_comma_list_minutes() -> None:
    after = _dt(2025, 1, 1, 12, 0)
    nxt = _cron_next("15,45 12 * * *", after)
    assert nxt == _dt(2025, 1, 1, 12, 15)


def test_cron_dow_monday() -> None:
    # 2025-01-06 is a Monday
    after = _dt(2025, 1, 5, 23, 59)  # Sunday
    nxt = _cron_next("0 9 * * 1", after)  # Monday = 1 in cron
    assert nxt.weekday() == 0  # Python Monday = 0
    assert nxt.hour == 9


def test_cron_dow_sunday_zero() -> None:
    # cron DOW 0 = Sunday; Python weekday() 6 = Sunday
    after = _dt(2025, 1, 4, 23, 59)  # Saturday
    nxt = _cron_next("0 10 * * 0", after)
    assert nxt.weekday() == 6  # Sunday


def test_cron_dow_sunday_seven() -> None:
    # DOW 7 also means Sunday in many cron implementations
    after = _dt(2025, 1, 4, 23, 59)
    nxt = _cron_next("0 10 * * 7", after)
    assert nxt.weekday() == 6  # Sunday


def test_cron_year_boundary() -> None:
    after = _dt(2025, 12, 31, 23, 58)
    nxt = _cron_next("0 0 1 1 *", after)
    assert nxt == _dt(2026, 1, 1, 0, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. _compute_next_run
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_interval_adds_seconds() -> None:
    t = _interval_task(seconds=300)
    from_time = _dt(2025, 1, 1, 12, 0)
    nxt = _compute_next_run(t, from_time)
    assert nxt == from_time + timedelta(seconds=300)


def test_compute_cron_returns_future() -> None:
    t = _cron_task(cron="0 8 * * *")
    from_time = _dt(2025, 1, 1, 7, 59)
    nxt = _compute_next_run(t, from_time)
    assert nxt == _dt(2025, 1, 1, 8, 0)


def test_compute_one_shot_no_schedule_returns_none() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True)
    nxt = _compute_next_run(t, _dt())
    assert nxt is None


def test_compute_interval_zero() -> None:
    t = _interval_task(seconds=0)
    from_time = _dt(2025, 6, 1, 0, 0)
    nxt = _compute_next_run(t, from_time)
    assert nxt == from_time


def test_compute_interval_preserves_timezone() -> None:
    t = _interval_task(seconds=60)
    from_time = _dt(2025, 1, 1)
    nxt = _compute_next_run(t, from_time)
    assert nxt.tzinfo == UTC


def test_compute_updates_task_after_run() -> None:
    t = _interval_task(seconds=3600)
    start = _dt(2025, 1, 1, 0, 0)
    nxt = _compute_next_run(t, start)
    assert nxt == _dt(2025, 1, 1, 1, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 7. _is_due
# ─────────────────────────────────────────────────────────────────────────────

def test_is_due_when_next_run_in_past() -> None:
    t = _interval_task()
    t.next_run = _dt(2025, 1, 1, 11, 0)
    now = _dt(2025, 1, 1, 12, 0)
    assert _is_due(t, now) is True


def test_is_due_when_next_run_equals_now() -> None:
    t = _interval_task()
    now = _dt(2025, 1, 1, 12, 0)
    t.next_run = now
    assert _is_due(t, now) is True


def test_not_due_when_next_run_in_future() -> None:
    t = _interval_task()
    t.next_run = _dt(2025, 1, 1, 13, 0)
    now = _dt(2025, 1, 1, 12, 0)
    assert _is_due(t, now) is False


def test_disabled_task_never_due() -> None:
    t = _interval_task()
    t.enabled = False
    t.next_run = _dt(2025, 1, 1, 0, 0)
    now = _dt(2025, 1, 1, 12, 0)
    assert _is_due(t, now) is False


def test_never_run_no_schedule_is_due() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True)
    assert t.next_run is None
    assert t.last_run is None
    assert _is_due(t, _dt()) is True


def test_already_run_no_schedule_not_due() -> None:
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True)
    t.last_run = _dt(2025, 1, 1)
    t.next_run = None
    assert _is_due(t, _dt(2025, 1, 1, 12, 0)) is False


def test_is_due_next_run_one_minute_ahead_not_due() -> None:
    t = _interval_task()
    now = _dt(2025, 1, 1, 12, 0)
    t.next_run = now + timedelta(seconds=1)
    assert _is_due(t, now) is False


# ─────────────────────────────────────────────────────────────────────────────
# 8. HeartbeatScheduler — registration
# ─────────────────────────────────────────────────────────────────────────────

def test_add_task_stores_it() -> None:
    s = HeartbeatScheduler()
    t = _interval_task(name="a")
    s.add_task(t)
    assert s.get_task("a") is t


def test_get_task_missing_returns_none() -> None:
    s = HeartbeatScheduler()
    assert s.get_task("no_such") is None


def test_list_tasks_empty() -> None:
    s = HeartbeatScheduler()
    assert s.list_tasks() == []


def test_list_tasks_returns_all() -> None:
    s = HeartbeatScheduler()
    s.add_task(_interval_task("a"))
    s.add_task(_interval_task("b"))
    names = {t.name for t in s.list_tasks()}
    assert names == {"a", "b"}


def test_remove_task_returns_true() -> None:
    s = HeartbeatScheduler()
    s.add_task(_interval_task("a"))
    assert s.remove_task("a") is True


def test_remove_missing_returns_false() -> None:
    s = HeartbeatScheduler()
    assert s.remove_task("nope") is False


def test_add_duplicate_overwrites() -> None:
    s = HeartbeatScheduler()
    h1, h2 = AsyncMock(), AsyncMock()
    s.add_task(ScheduledTask(name="x", handler=h1, interval_seconds=10))
    s.add_task(ScheduledTask(name="x", handler=h2, interval_seconds=20))
    assert s.get_task("x").handler is h2  # type: ignore[union-attr]


def test_task_count_property() -> None:
    s = HeartbeatScheduler()
    assert s.task_count == 0
    s.add_task(_interval_task("a"))
    assert s.task_count == 1
    s.remove_task("a")
    assert s.task_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 9. HeartbeatScheduler — _tick execution
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tick_calls_due_handler() -> None:
    s = HeartbeatScheduler()
    h = AsyncMock()
    t = _interval_task("a", handler=h)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    h.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_skips_non_due_task() -> None:
    s = HeartbeatScheduler()
    h = AsyncMock()
    t = _interval_task("a", handler=h)
    t.next_run = _dt(2025, 1, 1, 12, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 0))
    h.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_skips_disabled_task() -> None:
    s = HeartbeatScheduler()
    h = AsyncMock()
    t = _interval_task("a", handler=h)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    t.enabled = False
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    h.assert_not_awaited()


@pytest.mark.asyncio
async def test_tick_increments_run_count() -> None:
    s = HeartbeatScheduler()
    t = _interval_task("a", seconds=60)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.run_count == 1


@pytest.mark.asyncio
async def test_tick_updates_last_run() -> None:
    s = HeartbeatScheduler()
    t = _interval_task("a", seconds=60)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.last_run is not None


@pytest.mark.asyncio
async def test_tick_advances_next_run_for_interval_task() -> None:
    s = HeartbeatScheduler()
    t = _interval_task("a", seconds=3600)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.next_run > _dt(2025, 1, 1, 0, 1)


@pytest.mark.asyncio
async def test_tick_runs_multiple_due_tasks() -> None:
    s = HeartbeatScheduler()
    h1, h2 = AsyncMock(), AsyncMock()
    for name, h in [("a", h1), ("b", h2)]:
        t = _interval_task(name, handler=h)
        t.next_run = _dt(2025, 1, 1, 0, 0)
        s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    h1.assert_awaited_once()
    h2.assert_awaited_once()


@pytest.mark.asyncio
async def test_failing_task_does_not_affect_others() -> None:
    s = HeartbeatScheduler()
    bad = AsyncMock(side_effect=RuntimeError("boom"))
    good = AsyncMock()
    for name, h in [("bad", bad), ("good", good)]:
        t = _interval_task(name, handler=h)
        t.next_run = _dt(2025, 1, 1, 0, 0)
        s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    good.assert_awaited_once()


@pytest.mark.asyncio
async def test_error_increments_error_count() -> None:
    s = HeartbeatScheduler()
    t = ScheduledTask(
        name="a",
        handler=AsyncMock(side_effect=ValueError("err")),
        interval_seconds=60,
    )
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.error_count >= 1


@pytest.mark.asyncio
async def test_tick_empty_tasks_is_noop() -> None:
    s = HeartbeatScheduler()
    await s._tick(now=_dt())  # must not raise


@pytest.mark.asyncio
async def test_run_count_increments_on_each_tick() -> None:
    s = HeartbeatScheduler()
    t = _interval_task("a", seconds=0)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    now = _dt(2025, 1, 1, 0, 1)
    await s._tick(now=now)
    t.next_run = now  # reset to due again
    await s._tick(now=now)
    assert t.run_count == 2


@pytest.mark.asyncio
async def test_tick_cron_task_fires_when_due() -> None:
    s = HeartbeatScheduler()
    h = AsyncMock()
    t = _cron_task("morning", cron="0 8 * * *", handler=h)
    t.next_run = _dt(2025, 1, 1, 8, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 8, 0))
    h.assert_awaited_once()


@pytest.mark.asyncio
async def test_cron_task_next_run_advances_to_next_day() -> None:
    s = HeartbeatScheduler()
    t = _cron_task("daily", cron="0 8 * * *")
    t.next_run = _dt(2025, 1, 1, 8, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 8, 0))
    assert t.next_run is not None
    assert t.next_run >= _dt(2025, 1, 2, 8, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 10. HeartbeatScheduler — timeout & retries
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_increments_error_count() -> None:
    async def slow() -> None:
        await asyncio.sleep(10)

    s = HeartbeatScheduler()
    t = ScheduledTask(name="slow", handler=slow, interval_seconds=60, timeout_seconds=0.01)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.error_count >= 1


@pytest.mark.asyncio
async def test_timeout_does_not_increment_run_count() -> None:
    async def slow() -> None:
        await asyncio.sleep(10)

    s = HeartbeatScheduler()
    t = ScheduledTask(name="slow", handler=slow, interval_seconds=60, timeout_seconds=0.01)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.run_count == 0


@pytest.mark.asyncio
async def test_retry_on_failure() -> None:
    call_count = 0

    async def flaky() -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("not yet")

    s = HeartbeatScheduler()
    t = ScheduledTask(name="flaky", handler=flaky, interval_seconds=60, max_retries=2)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.run_count == 1
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_limit_respected() -> None:
    calls: list[int] = []

    async def always_fail() -> None:
        calls.append(1)
        raise RuntimeError("fail")

    s = HeartbeatScheduler()
    t = ScheduledTask(name="bad", handler=always_fail, interval_seconds=60, max_retries=2)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert len(calls) == 3  # 1 initial + 2 retries
    assert t.run_count == 0
    assert t.error_count == 3


@pytest.mark.asyncio
async def test_no_retry_by_default() -> None:
    calls: list[int] = []

    async def fail() -> None:
        calls.append(1)
        raise RuntimeError("err")

    s = HeartbeatScheduler()
    t = ScheduledTask(name="x", handler=fail, interval_seconds=60)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_success_after_retry_increments_run_count() -> None:
    attempt = 0

    async def sometimes_fail() -> None:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise RuntimeError("first attempt fails")

    s = HeartbeatScheduler()
    t = ScheduledTask(name="x", handler=sometimes_fail, interval_seconds=60, max_retries=1)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.run_count == 1
    assert t.error_count == 1


@pytest.mark.asyncio
async def test_error_count_accumulates_across_ticks() -> None:
    s = HeartbeatScheduler()
    t = ScheduledTask(
        name="x",
        handler=AsyncMock(side_effect=RuntimeError("err")),
        interval_seconds=0,
    )
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    now = _dt(2025, 1, 1, 0, 1)
    await s._tick(now=now)
    t.next_run = now
    await s._tick(now=now)
    assert t.error_count >= 2


# ─────────────────────────────────────────────────────────────────────────────
# 11. HeartbeatScheduler — one_shot
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_one_shot_disabled_after_run() -> None:
    s = HeartbeatScheduler()
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True, interval_seconds=60)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.enabled is False


@pytest.mark.asyncio
async def test_one_shot_does_not_run_twice() -> None:
    h = AsyncMock()
    s = HeartbeatScheduler()
    t = ScheduledTask(name="x", handler=h, one_shot=True, interval_seconds=0)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    now = _dt(2025, 1, 1, 0, 1)
    await s._tick(now=now)
    await s._tick(now=now)
    assert h.await_count == 1


@pytest.mark.asyncio
async def test_one_shot_no_schedule_fires_immediately() -> None:
    h = AsyncMock()
    s = HeartbeatScheduler()
    t = ScheduledTask(name="x", handler=h, one_shot=True)
    s.add_task(t, now=_dt(2025, 1, 1, 0, 0))
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    h.assert_awaited_once()


@pytest.mark.asyncio
async def test_one_shot_run_count_is_one() -> None:
    s = HeartbeatScheduler()
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True, interval_seconds=60)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.run_count == 1


@pytest.mark.asyncio
async def test_one_shot_next_run_is_none_after_fire() -> None:
    s = HeartbeatScheduler()
    # No interval/cron → next_run should be None after firing
    t = ScheduledTask(name="x", handler=AsyncMock(), one_shot=True)
    t.next_run = _dt(2025, 1, 1, 0, 0)
    s.add_task(t)
    await s._tick(now=_dt(2025, 1, 1, 0, 1))
    assert t.next_run is None


# ─────────────────────────────────────────────────────────────────────────────
# 12. HeartbeatScheduler — lifecycle (start/stop)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_running_false_before_start() -> None:
    s = HeartbeatScheduler()
    assert s.running is False


@pytest.mark.asyncio
async def test_running_true_after_start() -> None:
    s = HeartbeatScheduler()
    await s.start()
    assert s.running is True
    await s.stop()


@pytest.mark.asyncio
async def test_running_false_after_stop() -> None:
    s = HeartbeatScheduler()
    await s.start()
    await s.stop()
    assert s.running is False


@pytest.mark.asyncio
async def test_start_idempotent() -> None:
    s = HeartbeatScheduler()
    await s.start()
    await s.start()  # second call must not raise
    assert s.running is True
    await s.stop()


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    s = HeartbeatScheduler()
    await s.stop()  # stop without start must not raise
    await s.stop()


@pytest.mark.asyncio
async def test_task_added_before_start_runs_after_start() -> None:
    h = AsyncMock()
    s = HeartbeatScheduler(tick_interval=0.05)
    t = _interval_task("a", seconds=0, handler=h)
    t.next_run = datetime.now(UTC)
    s.add_task(t)
    await s.start()
    await asyncio.sleep(0.15)
    await s.stop()
    assert h.await_count >= 1


@pytest.mark.asyncio
async def test_scheduler_fires_task_periodically() -> None:
    h = AsyncMock()
    s = HeartbeatScheduler(tick_interval=0.05)
    t = _interval_task("a", seconds=0, handler=h)
    t.next_run = datetime.now(UTC)
    s.add_task(t)
    await s.start()
    await asyncio.sleep(0.25)
    await s.stop()
    assert h.await_count >= 2


# ─────────────────────────────────────────────────────────────────────────────
# 13. Gateway integration
# ─────────────────────────────────────────────────────────────────────────────

def test_gateway_lifespan_imports_scheduler() -> None:
    from cortexflow_ai.gateway.main import _build_lifespan
    assert callable(_build_lifespan)


@pytest.mark.asyncio
async def test_app_state_has_scheduler_after_lifespan() -> None:
    from cortexflow_ai.config import load_config
    from cortexflow_ai.gateway.main import _build_lifespan, create_app
    from cortexflow_ai.scheduler import HeartbeatScheduler

    cfg = load_config()
    app = create_app(cfg)
    # ASGITransport does not trigger lifespan; invoke the context manager directly
    async with _build_lifespan(cfg)(app):
        assert isinstance(app.state.scheduler, HeartbeatScheduler)


def test_scheduler_default_tick_interval() -> None:
    s = HeartbeatScheduler()
    assert s._tick_interval == HeartbeatScheduler.DEFAULT_TICK


def test_scheduler_custom_tick_interval() -> None:
    s = HeartbeatScheduler(tick_interval=120)
    assert s._tick_interval == 120
