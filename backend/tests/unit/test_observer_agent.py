"""
Unit tests for ObserverAgent, AgentSnapshot, and SystemSnapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.orchestration.observer_agent import (
    AgentSnapshot,
    ObserverAgent,
    SystemSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(task_id: str, agent_type: str, success: bool):
    """Build minimal mock orchestration-result objects."""
    decision = MagicMock()
    decision.task_id = task_id
    decision.assigned_agent_type = agent_type

    exec_res = MagicMock()
    exec_res.task_id = task_id
    exec_res.success = success

    orch = MagicMock()
    orch.routing_decisions = [decision]
    orch.execution_results = [exec_res]
    return orch


# ---------------------------------------------------------------------------
# AgentSnapshot
# ---------------------------------------------------------------------------


class TestAgentSnapshot:
    def test_to_dict_has_required_keys(self):
        snap = AgentSnapshot(agent_id="agent-1", status="idle")
        d = snap.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["status"] == "idle"
        assert "timestamp" in d
        assert "metadata" in d

    def test_default_metadata_is_empty(self):
        snap = AgentSnapshot(agent_id="a", status="active")
        assert snap.to_dict()["metadata"] == {}

    def test_custom_metadata_preserved(self):
        snap = AgentSnapshot(agent_id="a", status="idle", metadata={"role": "planner"})
        assert snap.to_dict()["metadata"]["role"] == "planner"

    def test_timestamp_is_iso_string(self):
        snap = AgentSnapshot(agent_id="a", status="idle")
        ts = snap.to_dict()["timestamp"]
        # Should parse without error
        datetime.fromisoformat(ts)


# ---------------------------------------------------------------------------
# SystemSnapshot
# ---------------------------------------------------------------------------


class TestSystemSnapshot:
    def _make(self, statuses: list[str]) -> SystemSnapshot:
        agents = [AgentSnapshot(agent_id=f"a{i}", status=s) for i, s in enumerate(statuses)]
        return SystemSnapshot(
            snapshot_id="snap-001",
            timestamp=datetime.now(timezone.utc),
            agents=agents,
        )

    def test_active_count(self):
        snap = self._make(["active", "idle", "active", "error"])
        assert snap.active_count == 2

    def test_healthy_count(self):
        snap = self._make(["active", "idle", "error", "unknown"])
        assert snap.healthy_count == 2

    def test_to_dict_structure(self):
        snap = self._make(["idle", "active"])
        d = snap.to_dict()
        assert d["snapshot_id"] == "snap-001"
        assert "timestamp" in d
        assert len(d["agents"]) == 2
        assert d["active_count"] == 1
        assert d["healthy_count"] == 2

    def test_empty_agents(self):
        snap = SystemSnapshot(snapshot_id="s", timestamp=datetime.now(timezone.utc))
        assert snap.active_count == 0
        assert snap.healthy_count == 0


# ---------------------------------------------------------------------------
# ObserverAgent — construction
# ---------------------------------------------------------------------------


class TestObserverAgentInit:
    def test_default_agent_id_generated(self):
        obs = ObserverAgent()
        assert obs.agent_id.startswith("observer-")

    def test_custom_agent_id(self):
        obs = ObserverAgent(agent_id="my-observer")
        assert obs.agent_id == "my-observer"

    def test_initial_counts_zero(self):
        obs = ObserverAgent()
        assert obs.agent_count == 0
        assert obs.active_agents == []


# ---------------------------------------------------------------------------
# ObserverAgent — registry management
# ---------------------------------------------------------------------------


class TestObserverAgentRegistry:
    def test_register_agent(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        assert obs.agent_count == 1

    def test_register_multiple_agents(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        obs.register_agent("router")
        obs.register_agent("executor")
        assert obs.agent_count == 3

    def test_register_duplicate_raises(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        with pytest.raises(ValueError, match="already registered"):
            obs.register_agent("planner")

    def test_register_with_metadata(self):
        obs = ObserverAgent()
        obs.register_agent("planner", metadata={"version": "1.0"})
        snap = obs.get_snapshot()
        assert snap.agents[0].metadata["version"] == "1.0"

    def test_unregister_agent(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        obs.unregister_agent("planner")
        assert obs.agent_count == 0

    def test_unregister_unknown_raises(self):
        obs = ObserverAgent()
        with pytest.raises(KeyError):
            obs.unregister_agent("ghost")

    def test_update_status_valid(self):
        obs = ObserverAgent()
        obs.register_agent("executor")
        obs.update_agent_status("executor", "active")
        assert "executor" in obs.active_agents

    def test_update_status_invalid_raises(self):
        obs = ObserverAgent()
        obs.register_agent("executor")
        with pytest.raises(ValueError, match="Invalid status"):
            obs.update_agent_status("executor", "sleeping")

    def test_update_status_unknown_agent_raises(self):
        obs = ObserverAgent()
        with pytest.raises(KeyError):
            obs.update_agent_status("ghost", "idle")

    def test_update_status_merges_metadata(self):
        obs = ObserverAgent()
        obs.register_agent("planner", metadata={"a": 1})
        obs.update_agent_status("planner", "active", metadata={"b": 2})
        snap = obs.get_snapshot()
        agent = snap.agents[0]
        assert agent.metadata["a"] == 1
        assert agent.metadata["b"] == 2


# ---------------------------------------------------------------------------
# ObserverAgent — active_agents property
# ---------------------------------------------------------------------------


class TestActiveAgents:
    def test_no_active_initially(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        obs.register_agent("router")
        assert obs.active_agents == []

    def test_active_agents_after_status_update(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        obs.register_agent("router")
        obs.update_agent_status("planner", "active")
        assert obs.active_agents == ["planner"]


# ---------------------------------------------------------------------------
# ObserverAgent — get_snapshot
# ---------------------------------------------------------------------------


class TestGetSnapshot:
    def test_snapshot_has_all_registered_agents(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        obs.register_agent("router")
        snap = obs.get_snapshot()
        agent_ids = {a.agent_id for a in snap.agents}
        assert agent_ids == {"planner", "router"}

    def test_snapshot_default_status_is_idle(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        snap = obs.get_snapshot()
        assert snap.agents[0].status == "idle"

    def test_snapshot_id_is_unique(self):
        obs = ObserverAgent()
        snap1 = obs.get_snapshot()
        snap2 = obs.get_snapshot()
        assert snap1.snapshot_id != snap2.snapshot_id


# ---------------------------------------------------------------------------
# ObserverAgent — observe (async)
# ---------------------------------------------------------------------------


class TestObserve:
    async def test_observe_returns_system_snapshot(self):
        obs = ObserverAgent()
        obs.register_agent("general")
        orch = _make_result("t1", "general", success=True)
        snap = await obs.observe(orch)
        assert isinstance(snap, SystemSnapshot)

    async def test_observe_marks_agent_idle_on_success(self):
        obs = ObserverAgent()
        obs.register_agent("executor")
        obs.update_agent_status("executor", "active")
        orch = _make_result("t1", "executor", success=True)
        snap = await obs.observe(orch)
        agent = next(a for a in snap.agents if a.agent_id == "executor")
        assert agent.status == "idle"

    async def test_observe_marks_agent_error_on_failure(self):
        obs = ObserverAgent()
        obs.register_agent("executor")
        orch = _make_result("t1", "executor", success=False)
        snap = await obs.observe(orch)
        agent = next(a for a in snap.agents if a.agent_id == "executor")
        assert agent.status == "error"

    async def test_observe_ignores_unregistered_agent_type(self):
        """Agents types not in registry should not cause errors."""
        obs = ObserverAgent()
        obs.register_agent("planner")
        orch = _make_result("t1", "unknown-type", success=True)
        snap = await obs.observe(orch)
        # planner status unchanged
        agent = next(a for a in snap.agents if a.agent_id == "planner")
        assert agent.status == "idle"

    async def test_observe_updates_last_snapshot(self):
        obs = ObserverAgent()
        orch = _make_result("t1", "x", success=True)
        snap = await obs.observe(orch)
        assert obs._last_snapshot is not None
        assert obs._last_snapshot.snapshot_id == snap.snapshot_id

    async def test_observe_multiple_routing_decisions(self):
        obs = ObserverAgent()
        obs.register_agent("agent-a")
        obs.register_agent("agent-b")

        d1 = MagicMock()
        d1.task_id = "t1"
        d1.assigned_agent_type = "agent-a"
        d2 = MagicMock()
        d2.task_id = "t2"
        d2.assigned_agent_type = "agent-b"
        e1 = MagicMock()
        e1.task_id = "t1"
        e1.success = True
        e2 = MagicMock()
        e2.task_id = "t2"
        e2.success = False

        orch = MagicMock()
        orch.routing_decisions = [d1, d2]
        orch.execution_results = [e1, e2]

        snap = await obs.observe(orch)
        statuses = {a.agent_id: a.status for a in snap.agents}
        assert statuses["agent-a"] == "idle"
        assert statuses["agent-b"] == "error"

    async def test_observe_empty_result(self):
        obs = ObserverAgent()
        obs.register_agent("planner")
        orch = MagicMock()
        orch.routing_decisions = []
        orch.execution_results = []
        snap = await obs.observe(orch)
        assert snap.active_count == 0
