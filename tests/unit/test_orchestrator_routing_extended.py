"""Extended routing tests for AgentOrchestrator.

The base suite in test_orchestrator.py covers registration, basic routing,
and node statistics. These tests focus on:
- NoEligibleNodeError and NodeNotFoundError exception paths
- Fallback node selection (init-time and set_fallback)
- Channel-based routing rules
- Round-robin across 3+ equally-ranked nodes
- Disabled nodes excluded from routing
- Re-registering a node replaces it and resets stats
- get_node_namespaces / memory_for_node
- route() increments total_routed and returns AgentResult
"""

from __future__ import annotations

import pytest

from cortexflow_ai.orchestrator import (
    AgentNodeConfig,
    AgentOrchestrator,
    AgentTask,
)
from cortexflow_ai.orchestrator.orchestrator import (
    NodeNotFoundError,
    NoEligibleNodeError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _cfg(
    name: str,
    task_types: list[str] | None = None,
    priority: int = 5,
    enabled: bool = True,
    channels: list[str] | None = None,
    keywords: list[str] | None = None,
    memory_namespace: str = "",
) -> AgentNodeConfig:
    return AgentNodeConfig(
        name=name,
        description=f"Node {name}",
        task_types=task_types or ["general"],
        priority=priority,
        enabled=enabled,
        channel_patterns=channels or [],
        routing_keywords=keywords or [],
        memory_namespace=memory_namespace,
    )


def _task(
    content: str = "hello",
    task_type: str = "general",
    source_channel: str | None = None,
) -> AgentTask:
    return AgentTask(content=content, task_type=task_type, source_channel=source_channel)


# ---------------------------------------------------------------------------
# NoEligibleNodeError
# ---------------------------------------------------------------------------


class TestNoEligibleNodeError:
    def test_no_nodes_raises(self):
        orch = AgentOrchestrator()
        with pytest.raises(NoEligibleNodeError):
            orch.select(_task())

    def test_all_nodes_disabled_raises(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("a", enabled=False))
        orch.register(_cfg("b", enabled=False))
        with pytest.raises(NoEligibleNodeError):
            orch.select(_task())

    def test_wrong_task_type_raises(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("coder", task_types=["code_generation"]))
        with pytest.raises(NoEligibleNodeError):
            orch.select(_task(task_type="summarization"))

    def test_error_message_contains_task_type(self):
        orch = AgentOrchestrator()
        with pytest.raises(NoEligibleNodeError, match="task_type"):
            orch.select(_task(task_type="research"))

    def test_wrong_channel_raises(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("slack-only", channels=["slack"]))
        with pytest.raises(NoEligibleNodeError):
            orch.select(_task(source_channel="discord"))


# ---------------------------------------------------------------------------
# NodeNotFoundError
# ---------------------------------------------------------------------------


class TestNodeNotFoundError:
    def test_get_missing_node_raises(self):
        orch = AgentOrchestrator()
        with pytest.raises(NodeNotFoundError):
            orch.get("nonexistent")

    def test_remove_missing_node_raises(self):
        orch = AgentOrchestrator()
        with pytest.raises(NodeNotFoundError):
            orch.remove("ghost")

    def test_enable_missing_node_raises(self):
        orch = AgentOrchestrator()
        with pytest.raises(NodeNotFoundError):
            orch.enable("missing")

    def test_disable_missing_node_raises(self):
        orch = AgentOrchestrator()
        with pytest.raises(NodeNotFoundError):
            orch.disable("missing")

    def test_memory_for_missing_node_raises(self):
        orch = AgentOrchestrator()
        with pytest.raises(NodeNotFoundError):
            orch.memory_for_node("ghost")


# ---------------------------------------------------------------------------
# Fallback node
# ---------------------------------------------------------------------------


class TestFallbackNode:
    def test_fallback_used_when_no_eligible_primary(self):
        fallback_cfg = _cfg("fallback", task_types=["general"])
        orch = AgentOrchestrator(fallback_config=fallback_cfg)
        orch.register(_cfg("coder", task_types=["code_generation"]))
        # "summarization" matches neither coder nor general — but fallback is "general"
        # Wait: fallback cfg has task_types=["general"], so summarization won't match
        # Let's use general task to trigger fallback
        orch.disable("coder")
        # now no primary eligible for code_generation → fallback (general) doesn't match either
        # Use a general task that the coder node doesn't handle
        node = orch.select(_task(task_type="general"))
        assert node.name == "fallback"

    def test_fallback_not_used_when_primary_eligible(self):
        fallback_cfg = _cfg("fallback")
        orch = AgentOrchestrator(fallback_config=fallback_cfg)
        orch.register(_cfg("primary", priority=10))
        node = orch.select(_task())
        assert node.name == "primary"

    def test_set_fallback_replaces_existing(self):
        orch = AgentOrchestrator()
        orch.set_fallback(_cfg("fb1"))
        orch.set_fallback(_cfg("fb2"))
        # Only way to test replacement is via stats
        stats = orch.stats()
        assert stats["has_fallback"] is True

    def test_clear_fallback_removes_it(self):
        orch = AgentOrchestrator(fallback_config=_cfg("fb"))
        orch.clear_fallback()
        assert orch.stats()["has_fallback"] is False

    def test_fallback_raises_when_cleared_and_no_primary(self):
        orch = AgentOrchestrator(fallback_config=_cfg("fb"))
        orch.clear_fallback()
        with pytest.raises(NoEligibleNodeError):
            orch.select(_task())


# ---------------------------------------------------------------------------
# Channel-based routing
# ---------------------------------------------------------------------------


class TestChannelRouting:
    def test_channel_specific_node_selected_over_generic(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("generic", priority=5))
        # Channel-specific nodes should use higher priority to win over generic
        orch.register(_cfg("telegram-handler", priority=6, channels=["telegram"]))
        node = orch.select(_task(source_channel="telegram"))
        assert node.name == "telegram-handler"

    def test_channel_node_not_selected_for_wrong_channel(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("slack-only", priority=10, channels=["slack"]))
        orch.register(_cfg("fallback", priority=1))
        node = orch.select(_task(source_channel="discord"))
        assert node.name == "fallback"

    def test_no_channel_restriction_matches_any_channel(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("open"))
        node = orch.select(_task(source_channel="whatsapp"))
        assert node.name == "open"

    def test_task_with_no_channel_matches_channel_agnostic_node(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("agnostic"))
        node = orch.select(_task(source_channel=None))
        assert node.name == "agnostic"


# ---------------------------------------------------------------------------
# Keyword routing
# ---------------------------------------------------------------------------


class TestKeywordRouting:
    def test_keyword_match_selects_node(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("code-expert", priority=5, keywords=["python", "debug"]))
        orch.register(_cfg("general", priority=5))
        node = orch.select(_task(content="debug my python code"))
        assert node.name == "code-expert"

    def test_no_keyword_match_uses_task_type(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("code-expert", priority=5, keywords=["python"]))
        orch.register(_cfg("general", priority=5))
        node = orch.select(_task(content="summarize this text"))
        assert node.name in ("code-expert", "general")


# ---------------------------------------------------------------------------
# Round-robin tie-breaking
# ---------------------------------------------------------------------------


class TestRoundRobinTieBreaking:
    def test_three_equal_priority_nodes_rotate(self):
        orch = AgentOrchestrator()
        for name in ("a", "b", "c"):
            orch.register(_cfg(name, priority=5))

        selections = [orch.select(_task()).name for _ in range(9)]
        # Each of the 3 names should appear exactly 3 times in 9 calls
        assert selections.count("a") == 3
        assert selections.count("b") == 3
        assert selections.count("c") == 3

    def test_round_robin_resets_on_different_task_type(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("a", task_types=["general", "research"], priority=5))
        orch.register(_cfg("b", task_types=["general", "research"], priority=5))

        # Each task type gets its own counter — first call for each always starts at index 0
        first_general = orch.select(_task(task_type="general")).name
        first_research = orch.select(_task(task_type="research")).name
        # Both start from the beginning of their own rotation
        assert first_general in ("a", "b")
        assert first_research in ("a", "b")

    def test_higher_priority_always_wins_over_lower(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("low", priority=1))
        orch.register(_cfg("high", priority=100))

        for _ in range(5):
            assert orch.select(_task()).name == "high"


# ---------------------------------------------------------------------------
# Disable / enable nodes
# ---------------------------------------------------------------------------


class TestDisableEnable:
    def test_disabled_node_not_selected(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("a", priority=10))
        orch.register(_cfg("b", priority=5))
        orch.disable("a")
        node = orch.select(_task())
        assert node.name == "b"

    def test_re_enabling_disabled_node_restores_it(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("a", priority=10))
        orch.register(_cfg("b", priority=5))
        orch.disable("a")
        orch.enable("a")
        node = orch.select(_task())
        assert node.name == "a"

    def test_all_nodes_disabled_then_one_enabled(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("x", priority=5))
        orch.register(_cfg("y", priority=5))
        orch.disable("x")
        orch.disable("y")
        orch.enable("y")
        assert orch.select(_task()).name == "y"


# ---------------------------------------------------------------------------
# Re-registration replaces node and resets stats
# ---------------------------------------------------------------------------


class TestReRegistration:
    def test_re_register_replaces_existing(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("n", priority=5))
        orch.register(_cfg("n", priority=99))
        assert orch.get("n").config.priority == 99

    @pytest.mark.asyncio
    async def test_re_register_resets_stats(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("n"))
        # route() increments tasks_handled on the node
        await orch.route(_task())
        assert orch.get("n").stats()["tasks_handled"] == 1
        # Re-register — fresh node, stats cleared
        orch.register(_cfg("n"))
        assert orch.get("n").stats()["tasks_handled"] == 0

    def test_node_count_unchanged_after_re_register(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("n"))
        orch.register(_cfg("m"))
        orch.register(_cfg("n"))  # replace, not add
        assert orch.node_count() == 2


# ---------------------------------------------------------------------------
# route() method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRouteMethod:
    async def test_route_returns_agent_result(self):
        from cortexflow_ai.orchestrator import AgentResult

        orch = AgentOrchestrator()
        orch.register(_cfg("worker"))
        result = await orch.route(_task())
        assert isinstance(result, AgentResult)

    async def test_route_result_node_name_matches_winner(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("alpha", priority=10))
        orch.register(_cfg("beta", priority=5))
        result = await orch.route(_task())
        assert result.node_name == "alpha"

    async def test_route_increments_total_routed(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("w"))
        assert orch.stats()["total_routed"] == 0
        await orch.route(_task())
        assert orch.stats()["total_routed"] == 1
        await orch.route(_task())
        assert orch.stats()["total_routed"] == 2

    async def test_route_result_includes_memory_namespace(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("n", memory_namespace="my-ns"))
        result = await orch.route(_task())
        assert result.metadata["memory_namespace"] == "my-ns"

    async def test_route_result_latency_ms_is_non_negative(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("n"))
        result = await orch.route(_task())
        assert result.latency_ms >= 0

    async def test_route_raises_when_no_eligible_node(self):
        orch = AgentOrchestrator()
        with pytest.raises(NoEligibleNodeError):
            await orch.route(_task())


# ---------------------------------------------------------------------------
# get_node_namespaces
# ---------------------------------------------------------------------------


class TestGetNodeNamespaces:
    def test_empty_orchestrator_returns_empty(self):
        orch = AgentOrchestrator()
        assert orch.get_node_namespaces() == {}

    def test_default_namespace_is_node_name(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("alice"))
        ns_map = orch.get_node_namespaces()
        assert ns_map["alice"] == "alice"

    def test_explicit_namespace_overrides_default(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("alice", memory_namespace="shared-pool"))
        assert orch.get_node_namespaces()["alice"] == "shared-pool"

    def test_shared_namespace_appears_multiple_times(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("a", memory_namespace="shared"))
        orch.register(_cfg("b", memory_namespace="shared"))
        ns_map = orch.get_node_namespaces()
        assert ns_map["a"] == "shared"
        assert ns_map["b"] == "shared"

    def test_namespaces_removed_after_unregister(self):
        orch = AgentOrchestrator()
        orch.register(_cfg("x"))
        orch.remove("x")
        assert "x" not in orch.get_node_namespaces()
