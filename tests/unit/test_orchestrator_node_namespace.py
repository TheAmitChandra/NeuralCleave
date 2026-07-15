"""Tests for memory_namespace on AgentNodeConfig and AgentNode, plus from_dict()."""

from __future__ import annotations

import pytest

from cortexflow_ai.orchestrator.node import AgentNode, AgentNodeConfig
from cortexflow_ai.orchestrator.orchestrator import AgentOrchestrator
from cortexflow_ai.orchestrator.task import AgentTask

# ---------------------------------------------------------------------------
# AgentNodeConfig.memory_namespace field
# ---------------------------------------------------------------------------


class TestAgentNodeConfigMemoryNamespace:
    def test_default_memory_namespace_empty_string(self):
        cfg = AgentNodeConfig(name="work")
        assert cfg.memory_namespace == ""

    def test_effective_namespace_defaults_to_node_name(self):
        cfg = AgentNodeConfig(name="work")
        assert cfg.effective_memory_namespace == "work"

    def test_explicit_namespace_stored(self):
        cfg = AgentNodeConfig(name="work", memory_namespace="shared-pool")
        assert cfg.memory_namespace == "shared-pool"

    def test_explicit_namespace_used_as_effective(self):
        cfg = AgentNodeConfig(name="work", memory_namespace="custom-ns")
        assert cfg.effective_memory_namespace == "custom-ns"

    def test_two_nodes_same_explicit_namespace_share(self):
        c1 = AgentNodeConfig(name="code", memory_namespace="shared")
        c2 = AgentNodeConfig(name="review", memory_namespace="shared")
        assert c1.effective_memory_namespace == c2.effective_memory_namespace

    def test_two_nodes_different_names_isolated_by_default(self):
        c1 = AgentNodeConfig(name="work")
        c2 = AgentNodeConfig(name="personal")
        assert c1.effective_memory_namespace != c2.effective_memory_namespace

    def test_to_dict_includes_memory_namespace(self):
        cfg = AgentNodeConfig(name="work", memory_namespace="my-ns")
        d = cfg.to_dict()
        assert d["memory_namespace"] == "my-ns"

    def test_to_dict_includes_effective_memory_namespace(self):
        cfg = AgentNodeConfig(name="work")
        d = cfg.to_dict()
        assert d["effective_memory_namespace"] == "work"

    def test_to_dict_effective_with_explicit_namespace(self):
        cfg = AgentNodeConfig(name="work", memory_namespace="pool")
        d = cfg.to_dict()
        assert d["effective_memory_namespace"] == "pool"

    def test_to_dict_has_all_fields(self):
        cfg = AgentNodeConfig(name="x")
        d = cfg.to_dict()
        expected = {
            "name", "description", "model_override", "task_types",
            "routing_keywords", "channel_patterns", "priority",
            "max_concurrent", "enabled", "memory_namespace",
            "effective_memory_namespace",
        }
        assert expected <= set(d.keys())


# ---------------------------------------------------------------------------
# AgentNodeConfig.from_dict()
# ---------------------------------------------------------------------------


class TestAgentNodeConfigFromDict:
    def test_from_dict_name(self):
        cfg = AgentNodeConfig.from_dict({"name": "mynode"})
        assert cfg.name == "mynode"

    def test_from_dict_description_default(self):
        cfg = AgentNodeConfig.from_dict({"name": "x"})
        assert cfg.description == ""

    def test_from_dict_description_set(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "description": "Does X"})
        assert cfg.description == "Does X"

    def test_from_dict_model_override_default_none(self):
        cfg = AgentNodeConfig.from_dict({"name": "x"})
        assert cfg.model_override is None

    def test_from_dict_model_override(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "model_override": "anthropic/claude-3"})
        assert cfg.model_override == "anthropic/claude-3"

    def test_from_dict_task_types(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "task_types": ["code_generation"]})
        assert cfg.task_types == ["code_generation"]

    def test_from_dict_routing_keywords(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "routing_keywords": ["python", "code"]})
        assert cfg.routing_keywords == ["python", "code"]

    def test_from_dict_channel_patterns(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "channel_patterns": ["slack*"]})
        assert cfg.channel_patterns == ["slack*"]

    def test_from_dict_priority(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "priority": 10})
        assert cfg.priority == 10

    def test_from_dict_max_concurrent(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "max_concurrent": 8})
        assert cfg.max_concurrent == 8

    def test_from_dict_enabled_false(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "enabled": False})
        assert cfg.enabled is False

    def test_from_dict_memory_namespace(self):
        cfg = AgentNodeConfig.from_dict({"name": "x", "memory_namespace": "my-ns"})
        assert cfg.memory_namespace == "my-ns"

    def test_from_dict_memory_namespace_default_empty(self):
        cfg = AgentNodeConfig.from_dict({"name": "x"})
        assert cfg.memory_namespace == ""

    def test_from_dict_roundtrip(self):
        original = AgentNodeConfig(
            name="code",
            description="Handles code tasks",
            model_override="anthropic/claude-3",
            task_types=["code_generation"],
            routing_keywords=["python"],
            channel_patterns=["slack*"],
            priority=5,
            max_concurrent=2,
            enabled=False,
            memory_namespace="code-pool",
        )
        restored = AgentNodeConfig.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.model_override == original.model_override
        assert restored.task_types == original.task_types
        assert restored.routing_keywords == original.routing_keywords
        assert restored.channel_patterns == original.channel_patterns
        assert restored.priority == original.priority
        assert restored.max_concurrent == original.max_concurrent
        assert restored.enabled == original.enabled
        assert restored.memory_namespace == original.memory_namespace

    def test_from_dict_missing_name_raises(self):
        with pytest.raises(KeyError):
            AgentNodeConfig.from_dict({"description": "no name"})

    def test_from_dict_invalid_name_raises(self):
        with pytest.raises(ValueError):
            AgentNodeConfig.from_dict({"name": "invalid name!"})


# ---------------------------------------------------------------------------
# AgentNode.memory_namespace property
# ---------------------------------------------------------------------------


class TestAgentNodeMemoryNamespace:
    def test_node_inherits_effective_namespace(self):
        cfg = AgentNodeConfig(name="work")
        node = AgentNode(cfg)
        assert node.memory_namespace == "work"

    def test_node_uses_explicit_namespace(self):
        cfg = AgentNodeConfig(name="work", memory_namespace="pool")
        node = AgentNode(cfg)
        assert node.memory_namespace == "pool"

    def test_node_name_unchanged(self):
        cfg = AgentNodeConfig(name="work", memory_namespace="pool")
        node = AgentNode(cfg)
        assert node.name == "work"
        assert node.memory_namespace == "pool"


# ---------------------------------------------------------------------------
# AgentOrchestrator integration — namespace in routing
# ---------------------------------------------------------------------------


class TestOrchestratorNamespaceIntegration:
    @pytest.fixture
    def orch(self):
        return AgentOrchestrator()

    @pytest.fixture
    def task(self):
        return AgentTask(content="write some code", task_type="code_generation")

    def test_route_result_has_memory_namespace(self, orch, task):
        import asyncio
        orch.register(AgentNodeConfig(name="code"))
        result = asyncio.get_event_loop().run_until_complete(orch.route(task))
        assert "memory_namespace" in result.metadata

    def test_route_result_namespace_equals_node_name(self, orch, task):
        import asyncio
        orch.register(AgentNodeConfig(name="code"))
        result = asyncio.get_event_loop().run_until_complete(orch.route(task))
        assert result.metadata["memory_namespace"] == "code"

    def test_route_result_namespace_uses_explicit(self, orch, task):
        import asyncio
        orch.register(AgentNodeConfig(name="code", memory_namespace="shared"))
        result = asyncio.get_event_loop().run_until_complete(orch.route(task))
        assert result.metadata["memory_namespace"] == "shared"

    def test_get_node_namespaces_returns_mapping(self, orch):
        orch.register(AgentNodeConfig(name="code"))
        orch.register(AgentNodeConfig(name="review"))
        ns_map = orch.get_node_namespaces()
        assert "code" in ns_map
        assert "review" in ns_map

    def test_get_node_namespaces_values(self, orch):
        orch.register(AgentNodeConfig(name="code", memory_namespace="dev"))
        orch.register(AgentNodeConfig(name="review"))
        ns_map = orch.get_node_namespaces()
        assert ns_map["code"] == "dev"
        assert ns_map["review"] == "review"

    def test_stats_includes_namespaces(self, orch):
        orch.register(AgentNodeConfig(name="work"))
        s = orch.stats()
        assert "namespaces" in s

    def test_memory_manager_attached(self, orch):
        from cortexflow_ai.orchestrator.memory import MemoryNamespaceManager
        assert isinstance(orch._memory_manager, MemoryNamespaceManager)

    def test_memory_for_node_returns_store(self, orch):
        from cortexflow_ai.orchestrator.memory import MemoryNamespaceStore
        orch.register(AgentNodeConfig(name="work"))
        store = orch.memory_for_node("work")
        assert isinstance(store, MemoryNamespaceStore)

    def test_memory_for_node_namespace_match(self, orch):
        orch.register(AgentNodeConfig(name="work"))
        store = orch.memory_for_node("work")
        assert store.namespace == "work"

    def test_memory_for_node_explicit_namespace(self, orch):
        orch.register(AgentNodeConfig(name="work", memory_namespace="pool"))
        store = orch.memory_for_node("work")
        assert store.namespace == "pool"

    def test_two_nodes_same_explicit_namespace_same_store(self, orch):
        orch.register(AgentNodeConfig(name="code", memory_namespace="shared"))
        orch.register(AgentNodeConfig(name="review", memory_namespace="shared"))
        s1 = orch.memory_for_node("code")
        s2 = orch.memory_for_node("review")
        assert s1 is s2

    def test_two_nodes_default_namespace_isolated(self, orch):
        orch.register(AgentNodeConfig(name="code"))
        orch.register(AgentNodeConfig(name="review"))
        s1 = orch.memory_for_node("code")
        s2 = orch.memory_for_node("review")
        assert s1 is not s2

    def test_memory_write_isolated_across_nodes(self, orch):
        orch.register(AgentNodeConfig(name="work"))
        orch.register(AgentNodeConfig(name="personal"))
        orch.memory_for_node("work").put("secret", "project-x")
        assert orch.memory_for_node("personal").get("secret") is None

    def test_memory_for_unknown_node_raises(self, orch):
        from cortexflow_ai.orchestrator.orchestrator import NodeNotFoundError
        with pytest.raises(NodeNotFoundError):
            orch.memory_for_node("does_not_exist")

    def test_custom_memory_manager_injected(self):
        from cortexflow_ai.orchestrator.memory import MemoryNamespaceManager
        mgr = MemoryNamespaceManager(default_max_entries=5)
        orch = AgentOrchestrator(memory_manager=mgr)
        assert orch._memory_manager is mgr
