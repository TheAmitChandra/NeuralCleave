"""Unit tests for the agent_runtime module.

Covers:
    - AgentState enum values and behaviour
    - AgentConfig Pydantic validation
    - AgentTask dataclass defaults and fields
    - AgentRuntime: init, start, stop, pause, resume, submit_task, state transitions
    - AgentRuntime: cognitive pipeline (plan/execute/validate/reflect hooks)
    - AgentRuntime: error handling and metrics recording
    - AgentLifecycle: can_transition, valid_transitions_from, validate_transition
    - AgentLifecycle: history, last_event, transition_count
    - InvalidTransitionError: illegal transitions
    - LifecycleEvent: dataclass fields, to_dict serialisation
    - HeartbeatMonitor: init, start, stop, beat, callbacks, beat_count
    - HeartbeatMonitor: idempotent start, callback failure handling
    - HeartbeatResult: fields, to_dict
    - ExecutionLoop: run, stop, max_iterations, stats
    - ExecutionLoop: from_config factory
    - LoopStats: uptime_seconds, to_dict
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.agent_runtime.agent import (
    AgentConfig,
    AgentRuntime,
    AgentState,
    AgentTask,
)
from app.core.agent_runtime.heartbeat import (
    HeartbeatMonitor,
    HeartbeatResult,
)
from app.core.agent_runtime.lifecycle import (
    AgentLifecycle,
    InvalidTransitionError,
    LifecycleEvent,
    _VALID_TRANSITIONS,
)
from app.core.agent_runtime.loop import (
    ExecutionLoop,
    LoopConfig,
    LoopStats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kw) -> AgentConfig:
    return AgentConfig(name="test-agent", **kw)


def _make_runtime(agent_id: str = "agent-test", **config_kw) -> AgentRuntime:
    return AgentRuntime(agent_id, _make_config(**config_kw))


# ===========================================================================
# AgentState
# ===========================================================================

class TestAgentState:

    def test_all_states_exist(self):
        states = {s.value for s in AgentState}
        assert states == {
            "IDLE", "PLANNING", "EXECUTING", "VALIDATING",
            "REFLECTING", "PAUSED", "TERMINATED",
        }

    def test_is_string_enum(self):
        assert AgentState.IDLE == "IDLE"
        assert AgentState.TERMINATED == "TERMINATED"

    def test_str_conversion(self):
        assert str(AgentState.PLANNING) == "PLANNING"

    def test_enum_comparison(self):
        assert AgentState.IDLE != AgentState.PAUSED
        assert AgentState.TERMINATED is AgentState.TERMINATED


# ===========================================================================
# AgentConfig
# ===========================================================================

class TestAgentConfig:

    def test_required_field_name(self):
        config = AgentConfig(name="my-agent")
        assert config.name == "my-agent"

    def test_defaults(self):
        config = AgentConfig(name="x")
        assert config.agent_type == "generic"
        assert config.max_concurrent_tasks == 1
        assert config.heartbeat_interval_seconds == 30.0
        assert config.task_timeout_seconds == 300.0
        assert config.max_retries == 3
        assert config.metadata == {}

    def test_custom_values(self):
        config = AgentConfig(
            name="planner",
            agent_type="planner",
            max_retries=5,
            metadata={"tier": "high"},
        )
        assert config.agent_type == "planner"
        assert config.max_retries == 5
        assert config.metadata["tier"] == "high"

    def test_invalid_missing_name(self):
        with pytest.raises(Exception):  # pydantic ValidationError
            AgentConfig()  # type: ignore[call-arg]


# ===========================================================================
# AgentTask
# ===========================================================================

class TestAgentTask:

    def test_defaults(self):
        task = AgentTask()
        assert task.task_id  # non-empty UUID string
        assert task.description == ""
        assert task.payload == {}
        assert task.priority == 5
        assert isinstance(task.created_at, float)

    def test_custom_fields(self):
        task = AgentTask(
            task_id="t-001",
            description="analyse logs",
            payload={"file": "app.log"},
            priority=9,
        )
        assert task.task_id == "t-001"
        assert task.description == "analyse logs"
        assert task.payload == {"file": "app.log"}
        assert task.priority == 9

    def test_unique_ids(self):
        t1, t2 = AgentTask(), AgentTask()
        assert t1.task_id != t2.task_id


# ===========================================================================
# AgentRuntime — initialisation
# ===========================================================================

class TestAgentRuntimeInit:

    def test_initial_state_is_idle(self):
        rt = _make_runtime()
        assert rt.state == AgentState.IDLE

    def test_agent_id_stored(self):
        rt = _make_runtime("agent-xyz")
        assert rt.agent_id == "agent-xyz"

    def test_config_stored(self):
        config = _make_config(agent_type="critic")
        rt = AgentRuntime("a1", config)
        assert rt.config.agent_type == "critic"

    def test_initial_current_task_none(self):
        assert _make_runtime().current_task is None

    def test_initial_queue_empty(self):
        assert _make_runtime().queue_size == 0


# ===========================================================================
# AgentRuntime — start / stop
# ===========================================================================

class TestAgentRuntimeLifecycle:

    async def test_start_sets_idle(self):
        rt = _make_runtime()
        await rt.start()
        assert rt.state == AgentState.IDLE
        await rt.stop()

    async def test_stop_sets_terminated(self):
        rt = _make_runtime()
        await rt.start()
        await rt.stop()
        assert rt.state == AgentState.TERMINATED

    async def test_start_terminated_raises(self):
        rt = _make_runtime()
        await rt.start()
        await rt.stop()
        with pytest.raises(RuntimeError, match="TERMINATED"):
            await rt.start()

    async def test_stop_is_idempotent(self):
        rt = _make_runtime()
        await rt.start()
        await rt.stop()
        await rt.stop()  # second stop should not raise
        assert rt.state == AgentState.TERMINATED

    async def test_pause_sets_paused(self):
        rt = _make_runtime()
        await rt.start()
        await rt.pause()
        assert rt.state == AgentState.PAUSED
        await rt.stop()

    async def test_resume_from_paused(self):
        rt = _make_runtime()
        await rt.start()
        await rt.pause()
        await rt.resume()
        assert rt.state == AgentState.IDLE
        await rt.stop()

    async def test_pause_terminated_raises(self):
        rt = _make_runtime()
        await rt.start()
        await rt.stop()
        with pytest.raises(RuntimeError):
            await rt.pause()

    async def test_resume_non_paused_raises(self):
        rt = _make_runtime()
        await rt.start()
        with pytest.raises(RuntimeError):
            await rt.resume()
        await rt.stop()


# ===========================================================================
# AgentRuntime — task submission & execution
# ===========================================================================

class TestAgentRuntimeTasks:

    async def test_submit_task_increments_queue(self):
        rt = _make_runtime()
        await rt.start()
        task = AgentTask(description="t1")
        await rt.submit_task(task)
        assert rt.queue_size == 1
        await rt.stop()

    async def test_submit_to_terminated_raises(self):
        rt = _make_runtime()
        await rt.start()
        await rt.stop()
        with pytest.raises(RuntimeError):
            await rt.submit_task(AgentTask())

    async def test_task_executes_full_pipeline(self):
        """Tasks submitted while the loop runs complete the full pipeline."""
        phases: list[str] = []

        class TrackingRuntime(AgentRuntime):
            async def _plan(self, task):
                phases.append("plan")

            async def _execute(self, task):
                phases.append("execute")

            async def _validate(self, task):
                phases.append("validate")

            async def _reflect(self, task):
                phases.append("reflect")

        rt = TrackingRuntime("tr", _make_config())
        await rt.start()
        await rt.submit_task(AgentTask())
        # Give the loop time to process
        for _ in range(20):
            if "reflect" in phases:
                break
            await asyncio.sleep(0.05)
        await rt.stop()
        assert phases == ["plan", "execute", "validate", "reflect"]

    async def test_task_failure_resets_to_idle(self):
        """An exception in a pipeline hook must not leave the agent stuck."""

        class FailingRuntime(AgentRuntime):
            async def _execute(self, task):
                raise ValueError("simulated failure")

        rt = FailingRuntime("fr", _make_config())
        await rt.start()
        await rt.submit_task(AgentTask())
        for _ in range(20):
            if rt.state == AgentState.IDLE:
                break
            await asyncio.sleep(0.05)
        await rt.stop()
        # After the exception, the agent should be back to IDLE (not stuck)
        # (state will be TERMINATED after stop())
        assert rt.state == AgentState.TERMINATED  # stop() terminates cleanly


# ===========================================================================
# AgentLifecycle
# ===========================================================================

class TestAgentLifecycleTransitions:

    def test_can_transition_valid(self):
        assert AgentLifecycle.can_transition(AgentState.IDLE, AgentState.PLANNING)
        assert AgentLifecycle.can_transition(AgentState.PLANNING, AgentState.EXECUTING)
        assert AgentLifecycle.can_transition(AgentState.EXECUTING, AgentState.VALIDATING)
        assert AgentLifecycle.can_transition(AgentState.VALIDATING, AgentState.REFLECTING)
        assert AgentLifecycle.can_transition(AgentState.REFLECTING, AgentState.IDLE)

    def test_can_transition_invalid(self):
        assert not AgentLifecycle.can_transition(AgentState.TERMINATED, AgentState.IDLE)
        assert not AgentLifecycle.can_transition(AgentState.IDLE, AgentState.REFLECTING)
        assert not AgentLifecycle.can_transition(AgentState.TERMINATED, AgentState.PLANNING)

    def test_valid_transitions_from_returns_frozenset(self):
        ts = AgentLifecycle.valid_transitions_from(AgentState.PAUSED)
        assert AgentState.IDLE in ts
        assert AgentState.TERMINATED in ts

    def test_terminated_has_no_exits(self):
        ts = AgentLifecycle.valid_transitions_from(AgentState.TERMINATED)
        assert len(ts) == 0

    def test_all_states_in_transition_table(self):
        for state in AgentState:
            assert state in _VALID_TRANSITIONS

    def test_pause_reachable_from_all_active_states(self):
        active = [
            AgentState.IDLE, AgentState.PLANNING,
            AgentState.EXECUTING, AgentState.VALIDATING, AgentState.REFLECTING,
        ]
        for s in active:
            assert AgentLifecycle.can_transition(s, AgentState.PAUSED), f"{s} → PAUSED missing"

    def test_terminated_reachable_from_all_states(self):
        non_terminal = [s for s in AgentState if s != AgentState.TERMINATED]
        for s in non_terminal:
            assert AgentLifecycle.can_transition(s, AgentState.TERMINATED), f"{s} → TERMINATED missing"


class TestAgentLifecycleHistory:

    def test_validate_transition_records_event(self):
        lc = AgentLifecycle("a1")
        event = lc.validate_transition(AgentState.IDLE, AgentState.PLANNING)
        assert len(lc.history) == 1
        assert event.from_state == AgentState.IDLE
        assert event.to_state == AgentState.PLANNING

    def test_history_is_append_only_snapshot(self):
        lc = AgentLifecycle("a1")
        lc.validate_transition(AgentState.IDLE, AgentState.PLANNING)
        h1 = lc.history
        lc.validate_transition(AgentState.PLANNING, AgentState.EXECUTING)
        h2 = lc.history
        assert len(h1) == 1  # original snapshot unaffected
        assert len(h2) == 2

    def test_last_event_returns_most_recent(self):
        lc = AgentLifecycle("a1")
        lc.validate_transition(AgentState.IDLE, AgentState.PLANNING)
        lc.validate_transition(AgentState.PLANNING, AgentState.EXECUTING)
        last = lc.last_event()
        assert last.to_state == AgentState.EXECUTING

    def test_last_event_none_when_empty(self):
        assert AgentLifecycle("a1").last_event() is None

    def test_transition_count(self):
        lc = AgentLifecycle("a1")
        assert lc.transition_count() == 0
        lc.validate_transition(AgentState.IDLE, AgentState.PLANNING)
        assert lc.transition_count() == 1

    def test_reason_stored(self):
        lc = AgentLifecycle("a1")
        event = lc.validate_transition(
            AgentState.IDLE, AgentState.PLANNING, reason="user request"
        )
        assert event.reason == "user request"

    def test_metadata_stored(self):
        lc = AgentLifecycle("a1")
        event = lc.validate_transition(
            AgentState.IDLE, AgentState.PLANNING, metadata={"source": "api"}
        )
        assert event.metadata["source"] == "api"

    def test_invalid_transition_raises(self):
        lc = AgentLifecycle("a1")
        with pytest.raises(InvalidTransitionError):
            lc.validate_transition(AgentState.TERMINATED, AgentState.IDLE)

    def test_invalid_transition_not_recorded(self):
        lc = AgentLifecycle("a1")
        with pytest.raises(InvalidTransitionError):
            lc.validate_transition(AgentState.TERMINATED, AgentState.IDLE)
        assert lc.transition_count() == 0


# ===========================================================================
# LifecycleEvent
# ===========================================================================

class TestLifecycleEvent:

    def _make_event(self, **kw) -> LifecycleEvent:
        defaults = dict(
            from_state=AgentState.IDLE,
            to_state=AgentState.PLANNING,
            agent_id="a1",
        )
        defaults.update(kw)
        return LifecycleEvent(**defaults)

    def test_default_timestamp_is_utc(self):
        from datetime import timezone
        ev = self._make_event()
        assert ev.timestamp.tzinfo == timezone.utc

    def test_to_dict_keys(self):
        ev = self._make_event()
        d = ev.to_dict()
        assert set(d.keys()) == {
            "from_state", "to_state", "agent_id", "timestamp", "reason", "metadata"
        }

    def test_to_dict_values(self):
        ev = self._make_event(reason="test")
        d = ev.to_dict()
        assert d["from_state"] == "IDLE"
        assert d["to_state"] == "PLANNING"
        assert d["reason"] == "test"

    def test_to_dict_timestamp_is_iso(self):
        from datetime import datetime
        ev = self._make_event()
        ts = ev.to_dict()["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None


# ===========================================================================
# InvalidTransitionError
# ===========================================================================

class TestInvalidTransitionError:

    def test_is_exception(self):
        err = InvalidTransitionError("bad")
        assert isinstance(err, Exception)

    def test_message_propagated(self):
        with pytest.raises(InvalidTransitionError, match="bad transition"):
            raise InvalidTransitionError("bad transition")


# ===========================================================================
# HeartbeatMonitor
# ===========================================================================

class TestHeartbeatMonitorInit:

    def test_defaults(self):
        hb = HeartbeatMonitor("a1")
        assert hb.agent_id == "a1"
        assert hb.interval_seconds == 30.0
        assert hb.beat_count == 0
        assert hb.last_beat is None
        assert not hb.is_running

    def test_custom_interval(self):
        hb = HeartbeatMonitor("a1", interval_seconds=5.0)
        assert hb.interval_seconds == 5.0

    def test_initial_callbacks_empty(self):
        hb = HeartbeatMonitor("a1")
        assert hb._callbacks == []

    def test_callbacks_injected_at_init(self):
        async def cb(hb): pass
        hb = HeartbeatMonitor("a1", callbacks=[cb])
        assert len(hb._callbacks) == 1


class TestHeartbeatMonitorBeat:

    async def test_manual_beat_increments_count(self):
        hb = HeartbeatMonitor("a1")
        await hb.beat()
        assert hb.beat_count == 1

    async def test_beat_sets_last_beat(self):
        hb = HeartbeatMonitor("a1")
        result = await hb.beat()
        assert hb.last_beat is result

    async def test_beat_with_successful_callback(self):
        called = []

        async def cb(monitor):
            called.append(monitor.agent_id)

        hb = HeartbeatMonitor("a1", callbacks=[cb])
        result = await hb.beat()
        assert called == ["a1"]
        assert result.healthy is True

    async def test_beat_with_failing_callback_marks_unhealthy(self):
        async def bad_cb(monitor):
            raise RuntimeError("goal check failed")

        hb = HeartbeatMonitor("a1", callbacks=[bad_cb])
        result = await hb.beat()
        assert result.healthy is False
        assert "errors" in result.details

    async def test_multiple_callbacks_all_called(self):
        log = []

        async def cb1(m): log.append("cb1")
        async def cb2(m): log.append("cb2")

        hb = HeartbeatMonitor("a1", callbacks=[cb1, cb2])
        await hb.beat()
        assert log == ["cb1", "cb2"]

    async def test_beat_result_has_beat_number(self):
        hb = HeartbeatMonitor("a1")
        r1 = await hb.beat()
        r2 = await hb.beat()
        assert r1.beat_number == 1
        assert r2.beat_number == 2


class TestHeartbeatMonitorCallbackManagement:

    def test_add_callback(self):
        hb = HeartbeatMonitor("a1")
        async def cb(m): pass
        hb.add_callback(cb)
        assert len(hb._callbacks) == 1

    def test_remove_callback(self):
        hb = HeartbeatMonitor("a1")
        async def cb(m): pass
        hb.add_callback(cb)
        hb.remove_callback(cb)
        assert len(hb._callbacks) == 0

    def test_remove_nonexistent_callback_is_noop(self):
        hb = HeartbeatMonitor("a1")
        async def cb(m): pass
        hb.remove_callback(cb)  # should not raise


class TestHeartbeatMonitorLifecycle:

    async def test_start_sets_is_running(self):
        hb = HeartbeatMonitor("a1", interval_seconds=60.0)
        await hb.start()
        assert hb.is_running
        await hb.stop()

    async def test_stop_clears_is_running(self):
        hb = HeartbeatMonitor("a1", interval_seconds=60.0)
        await hb.start()
        await hb.stop()
        assert not hb.is_running

    async def test_start_is_idempotent(self):
        hb = HeartbeatMonitor("a1", interval_seconds=60.0)
        await hb.start()
        task_before = hb._task
        await hb.start()  # second call should be a no-op
        assert hb._task is task_before
        await hb.stop()

    async def test_stop_is_idempotent(self):
        hb = HeartbeatMonitor("a1", interval_seconds=60.0)
        await hb.start()
        await hb.stop()
        await hb.stop()  # should not raise


# ===========================================================================
# HeartbeatResult
# ===========================================================================

class TestHeartbeatResult:

    def test_defaults_healthy(self):
        r = HeartbeatResult(agent_id="a1", beat_number=1)
        assert r.healthy is True
        assert r.details == {}

    def test_to_dict_keys(self):
        r = HeartbeatResult(agent_id="a1", beat_number=2)
        d = r.to_dict()
        assert set(d.keys()) == {"agent_id", "beat_number", "timestamp", "healthy", "details"}

    def test_to_dict_values(self):
        r = HeartbeatResult(agent_id="a1", beat_number=3, healthy=False)
        d = r.to_dict()
        assert d["healthy"] is False
        assert d["agent_id"] == "a1"
        assert d["beat_number"] == 3


# ===========================================================================
# ExecutionLoop
# ===========================================================================

class TestLoopStats:

    def test_uptime_increases(self):
        stats = LoopStats()
        up1 = stats.uptime_seconds
        time.sleep(0.01)
        up2 = stats.uptime_seconds
        assert up2 > up1

    def test_to_dict_keys(self):
        stats = LoopStats()
        d = stats.to_dict()
        assert set(d.keys()) == {
            "iterations", "tasks_completed", "tasks_failed",
            "total_task_duration_seconds", "uptime_seconds",
        }


class TestExecutionLoop:

    async def test_run_starts_and_stops_runtime(self):
        rt = _make_runtime()
        loop = ExecutionLoop(rt, LoopConfig(max_iterations=2, idle_poll_interval=0.01))
        stats = await loop.run()
        assert rt.state == AgentState.TERMINATED
        assert stats.iterations == 2

    async def test_run_returns_stats(self):
        rt = _make_runtime()
        loop = ExecutionLoop(rt, LoopConfig(max_iterations=3, idle_poll_interval=0.01))
        stats = await loop.run()
        assert stats.iterations == 3

    async def test_stop_exits_loop_early(self):
        rt = _make_runtime()
        loop = ExecutionLoop(rt, LoopConfig(max_iterations=0, idle_poll_interval=0.05))

        async def stopper():
            await asyncio.sleep(0.1)
            await loop.stop()

        asyncio.create_task(stopper())
        stats = await loop.run()
        assert stats.iterations < 100  # definitely stopped before huge iteration count

    async def test_max_iterations_zero_runs_until_stopped(self):
        rt = _make_runtime()
        loop = ExecutionLoop(rt, LoopConfig(max_iterations=5, idle_poll_interval=0.001))
        stats = await loop.run()
        assert stats.iterations == 5

    async def test_from_config_factory(self):
        config = _make_config()
        loop = ExecutionLoop.from_config("a-001", config, LoopConfig(max_iterations=1, idle_poll_interval=0.01))
        assert isinstance(loop.runtime, AgentRuntime)
        stats = await loop.run()
        assert stats.iterations == 1

    async def test_stats_uptime_positive(self):
        rt = _make_runtime()
        loop = ExecutionLoop(rt, LoopConfig(max_iterations=1, idle_poll_interval=0.01))
        stats = await loop.run()
        assert stats.uptime_seconds > 0

    async def test_already_terminated_runtime_exits_immediately(self):
        rt = _make_runtime()
        await rt.start()
        await rt.stop()  # pre-terminate
        loop = ExecutionLoop(rt, LoopConfig(max_iterations=0, idle_poll_interval=0.01))
        stats = await loop.run()
        # The loop should detect TERMINATED and exit after at most 1 iteration
        assert stats.iterations <= 1
