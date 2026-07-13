"""Tests for cortexflow_ai/orchestrator/ — AgentTask, AgentResult,
AgentNodeConfig, AgentNode, AgentOrchestrator, REST routes, and CLI.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from cortexflow_ai.orchestrator.node import AgentNode, AgentNodeConfig, _glob_to_regex
from cortexflow_ai.orchestrator.orchestrator import (
    AgentOrchestrator,
    NodeNotFoundError,
    NoEligibleNodeError,
)
from cortexflow_ai.orchestrator.task import KNOWN_TASK_TYPES, AgentResult, AgentTask

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    name: str = "n",
    task_types: list[str] | None = None,
    keywords: list[str] | None = None,
    channels: list[str] | None = None,
    priority: int = 0,
    enabled: bool = True,
    model: str | None = None,
) -> AgentNodeConfig:
    return AgentNodeConfig(
        name=name,
        task_types=task_types or [],
        routing_keywords=keywords or [],
        channel_patterns=channels or [],
        priority=priority,
        enabled=enabled,
        model_override=model,
    )


def _task(
    content: str = "hello",
    task_type: str = "general",
    channel: str | None = None,
    session_id: str = "",
) -> AgentTask:
    return AgentTask(
        content=content,
        task_type=task_type,
        source_channel=channel,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# KNOWN_TASK_TYPES
# ---------------------------------------------------------------------------


def test_known_task_types_contains_general() -> None:
    assert "general" in KNOWN_TASK_TYPES


def test_known_task_types_contains_code_generation() -> None:
    assert "code_generation" in KNOWN_TASK_TYPES


def test_known_task_types_is_frozenset() -> None:
    assert isinstance(KNOWN_TASK_TYPES, frozenset)


# ---------------------------------------------------------------------------
# AgentTask
# ---------------------------------------------------------------------------


def test_task_defaults() -> None:
    t = AgentTask(content="hi")
    assert t.task_type == "general"
    assert t.session_id == ""
    assert t.source_channel is None
    assert t.timeout == 60.0
    assert t.metadata == {}


def test_task_empty_content_raises() -> None:
    with pytest.raises(ValueError, match="content"):
        AgentTask(content="")


def test_task_zero_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout"):
        AgentTask(content="x", timeout=0)


def test_task_negative_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout"):
        AgentTask(content="x", timeout=-1.0)


def test_task_to_dict_keys() -> None:
    t = AgentTask(content="hello", task_type="code_generation", source_channel="slack")
    d = t.to_dict()
    assert set(d.keys()) == {"content", "session_id", "task_type", "source_channel", "metadata", "timeout"}


def test_task_to_dict_values() -> None:
    t = AgentTask(content="test", task_type="research", source_channel="discord")
    d = t.to_dict()
    assert d["content"] == "test"
    assert d["task_type"] == "research"
    assert d["source_channel"] == "discord"


def test_task_metadata_stored() -> None:
    t = AgentTask(content="x", metadata={"key": "val"})
    assert t.metadata["key"] == "val"


# ---------------------------------------------------------------------------
# AgentResult
# ---------------------------------------------------------------------------


def test_result_defaults() -> None:
    r = AgentResult(content="out", node_name="n", task_type="general")
    assert r.latency_ms == 0.0
    assert r.metadata == {}


def test_result_to_dict_keys() -> None:
    r = AgentResult(content="out", node_name="x", task_type="general")
    assert set(r.to_dict().keys()) == {"content", "node_name", "task_type", "latency_ms", "metadata"}


def test_result_to_dict_values() -> None:
    r = AgentResult(content="ans", node_name="mynode", task_type="code_generation", latency_ms=42.5)
    d = r.to_dict()
    assert d["node_name"] == "mynode"
    assert d["latency_ms"] == 42.5


# ---------------------------------------------------------------------------
# _glob_to_regex
# ---------------------------------------------------------------------------


def test_glob_star_matches_anything() -> None:
    import re
    assert re.fullmatch(_glob_to_regex("*"), "anything")


def test_glob_star_matches_partial() -> None:
    import re
    assert re.fullmatch(_glob_to_regex("slack*"), "slack-team")


def test_glob_question_matches_single_char() -> None:
    import re
    assert re.fullmatch(_glob_to_regex("sla?k"), "slack")


def test_glob_literal_no_match() -> None:
    import re
    assert not re.fullmatch(_glob_to_regex("discord"), "slack")


# ---------------------------------------------------------------------------
# AgentNodeConfig — construction
# ---------------------------------------------------------------------------


def test_nodeconfig_valid() -> None:
    cfg = AgentNodeConfig(name="my-node")
    assert cfg.name == "my-node"
    assert cfg.enabled is True
    assert cfg.priority == 0


def test_nodeconfig_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="name"):
        AgentNodeConfig(name="")


def test_nodeconfig_invalid_name_raises() -> None:
    with pytest.raises(ValueError, match="invalid characters"):
        AgentNodeConfig(name="my node!")


def test_nodeconfig_name_with_underscore_ok() -> None:
    cfg = AgentNodeConfig(name="my_node")
    assert cfg.name == "my_node"


def test_nodeconfig_name_with_hyphen_ok() -> None:
    cfg = AgentNodeConfig(name="my-node")
    assert cfg.name == "my-node"


def test_nodeconfig_max_concurrent_zero_raises() -> None:
    with pytest.raises(ValueError, match="max_concurrent"):
        AgentNodeConfig(name="n", max_concurrent=0)


def test_nodeconfig_to_dict_all_keys() -> None:
    cfg = AgentNodeConfig(name="n", description="desc", model_override="a/b")
    d = cfg.to_dict()
    assert set(d.keys()) == {
        "name", "description", "model_override", "task_types",
        "routing_keywords", "channel_patterns", "priority", "max_concurrent", "enabled",
    }


# ---------------------------------------------------------------------------
# AgentNodeConfig — routing predicates
# ---------------------------------------------------------------------------


def test_matches_task_type_empty_accepts_any() -> None:
    cfg = _node()
    assert cfg.matches_task_type("code_generation")
    assert cfg.matches_task_type("unknown_type")


def test_matches_task_type_restricted() -> None:
    cfg = _node(task_types=["code_generation"])
    assert cfg.matches_task_type("code_generation")
    assert not cfg.matches_task_type("summarization")


def test_matches_keywords_empty_accepts_any() -> None:
    cfg = _node()
    assert cfg.matches_keywords("anything goes here")


def test_matches_keywords_found() -> None:
    cfg = _node(keywords=["python", "code"])
    assert cfg.matches_keywords("Write a python script")


def test_matches_keywords_case_insensitive() -> None:
    cfg = _node(keywords=["Python"])
    assert cfg.matches_keywords("write some python code")


def test_matches_keywords_not_found() -> None:
    cfg = _node(keywords=["java"])
    assert not cfg.matches_keywords("python code please")


def test_matches_channel_empty_accepts_any() -> None:
    cfg = _node()
    assert cfg.matches_channel("slack")
    assert cfg.matches_channel(None)


def test_matches_channel_specific() -> None:
    cfg = _node(channels=["slack"])
    assert cfg.matches_channel("slack")
    assert not cfg.matches_channel("discord")


def test_matches_channel_glob_star() -> None:
    cfg = _node(channels=["slack*"])
    assert cfg.matches_channel("slack-team")
    assert not cfg.matches_channel("discord")


def test_matches_channel_none_with_restriction() -> None:
    cfg = _node(channels=["slack"])
    assert not cfg.matches_channel(None)


def test_matches_channel_case_insensitive() -> None:
    cfg = _node(channels=["Slack"])
    assert cfg.matches_channel("slack")


def test_can_handle_all_match() -> None:
    cfg = _node(task_types=["code_generation"], keywords=["python"], channels=["slack"])
    t = _task(content="write python code", task_type="code_generation", channel="slack")
    assert cfg.can_handle(t)


def test_can_handle_disabled() -> None:
    cfg = _node(enabled=False)
    assert not cfg.can_handle(_task())


def test_can_handle_task_type_mismatch() -> None:
    cfg = _node(task_types=["code_generation"])
    assert not cfg.can_handle(_task(task_type="summarization"))


def test_can_handle_keyword_mismatch() -> None:
    cfg = _node(keywords=["java"])
    assert not cfg.can_handle(_task(content="python code"))


def test_can_handle_channel_mismatch() -> None:
    cfg = _node(channels=["slack"])
    assert not cfg.can_handle(_task(channel="discord"))


# ---------------------------------------------------------------------------
# AgentNode
# ---------------------------------------------------------------------------


def test_agentnode_name_from_config() -> None:
    node = AgentNode(_node(name="mynode"))
    assert node.name == "mynode"


def test_agentnode_can_handle_delegates_to_config() -> None:
    node = AgentNode(_node(task_types=["code_generation"]))
    assert node.can_handle(_task(task_type="code_generation"))
    assert not node.can_handle(_task(task_type="general"))


def test_agentnode_stats_initial() -> None:
    node = AgentNode(_node())
    s = node.stats()
    assert s["tasks_handled"] == 0
    assert s["errors"] == 0
    assert s["avg_latency_ms"] == 0.0


def test_agentnode_record_result_updates_stats() -> None:
    node = AgentNode(_node())
    result = AgentResult(content="x", node_name="n", task_type="general", latency_ms=50.0)
    node.record_result(result)
    s = node.stats()
    assert s["tasks_handled"] == 1
    assert s["avg_latency_ms"] == 50.0


def test_agentnode_record_error_updates_stats() -> None:
    node = AgentNode(_node())
    node.record_error()
    assert node.stats()["errors"] == 1


def test_agentnode_avg_latency_multiple_results() -> None:
    node = AgentNode(_node())
    for ms in [10.0, 20.0, 30.0]:
        node.record_result(AgentResult(content="", node_name="n", task_type="g", latency_ms=ms))
    assert node.stats()["avg_latency_ms"] == 20.0


# ---------------------------------------------------------------------------
# AgentOrchestrator — registration
# ---------------------------------------------------------------------------


def test_orchestrator_register_returns_node() -> None:
    orch = AgentOrchestrator()
    node = orch.register(_node("alpha"))
    assert isinstance(node, AgentNode)
    assert node.name == "alpha"


def test_orchestrator_register_adds_to_list() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("a"))
    orch.register(_node("b"))
    assert orch.node_count() == 2


def test_orchestrator_register_replaces_existing() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("a", priority=0))
    orch.register(_node("a", priority=5))
    assert orch.node_count() == 1
    assert orch.get("a").config.priority == 5


def test_orchestrator_list_nodes() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("x"))
    orch.register(_node("y"))
    names = [c.name for c in orch.list_nodes()]
    assert "x" in names
    assert "y" in names


def test_orchestrator_remove_existing() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("a"))
    orch.remove("a")
    assert orch.node_count() == 0


def test_orchestrator_remove_missing_raises() -> None:
    orch = AgentOrchestrator()
    with pytest.raises(NodeNotFoundError):
        orch.remove("ghost")


def test_orchestrator_get_existing() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("z"))
    assert orch.get("z").name == "z"


def test_orchestrator_get_missing_raises() -> None:
    orch = AgentOrchestrator()
    with pytest.raises(NodeNotFoundError):
        orch.get("nope")


def test_orchestrator_enable_disable() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("a"))
    orch.disable("a")
    assert not orch.get("a").config.enabled
    orch.enable("a")
    assert orch.get("a").config.enabled


# ---------------------------------------------------------------------------
# AgentOrchestrator — fallback
# ---------------------------------------------------------------------------


def test_orchestrator_fallback_used_when_no_match() -> None:
    orch = AgentOrchestrator(fallback_config=_node("fb"))
    orch.register(_node("specific", task_types=["code_generation"]))
    node = orch.select(_task(task_type="summarization"))
    assert node.name == "fb"


def test_orchestrator_fallback_not_used_when_match_exists() -> None:
    orch = AgentOrchestrator(fallback_config=_node("fb"))
    orch.register(_node("specific", task_types=["code_generation"]))
    node = orch.select(_task(task_type="code_generation"))
    assert node.name == "specific"


def test_orchestrator_set_fallback() -> None:
    orch = AgentOrchestrator()
    orch.set_fallback(_node("fb2"))
    orch.register(_node("nope", task_types=["code_generation"]))
    node = orch.select(_task(task_type="general"))
    assert node.name == "fb2"


def test_orchestrator_clear_fallback() -> None:
    orch = AgentOrchestrator(fallback_config=_node("fb"))
    orch.clear_fallback()
    orch.register(_node("specific", task_types=["code_generation"]))
    with pytest.raises(NoEligibleNodeError):
        orch.select(_task(task_type="summarization"))


# ---------------------------------------------------------------------------
# AgentOrchestrator — routing
# ---------------------------------------------------------------------------


def test_orchestrator_select_single_eligible() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("coder", task_types=["code_generation"]))
    orch.register(_node("writer", task_types=["creative"]))
    node = orch.select(_task(task_type="code_generation"))
    assert node.name == "coder"


def test_orchestrator_select_no_eligible_raises() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("coder", task_types=["code_generation"]))
    with pytest.raises(NoEligibleNodeError):
        orch.select(_task(task_type="summarization"))


def test_orchestrator_select_empty_raises() -> None:
    orch = AgentOrchestrator()
    with pytest.raises(NoEligibleNodeError):
        orch.select(_task())


def test_orchestrator_priority_wins() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("low", priority=0))
    orch.register(_node("high", priority=10))
    node = orch.select(_task())
    assert node.name == "high"


def test_orchestrator_priority_wins_reverse_registration() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("high", priority=10))
    orch.register(_node("low", priority=0))
    node = orch.select(_task())
    assert node.name == "high"


def test_orchestrator_round_robin_tied_priority() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("a", priority=5))
    orch.register(_node("b", priority=5))
    first = orch.select(_task())
    second = orch.select(_task())
    # Both should eventually be selected (order depends on dict insertion order)
    assert {first.name, second.name} == {"a", "b"}


def test_orchestrator_disabled_node_skipped() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("active"))
    orch.register(_node("inactive", enabled=False))
    node = orch.select(_task())
    assert node.name == "active"


def test_orchestrator_keyword_routing() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("python", keywords=["python"]))
    orch.register(_node("java", keywords=["java"]))
    node = orch.select(_task(content="write a python class"))
    assert node.name == "python"


def test_orchestrator_channel_routing() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("slack-node", channels=["slack"]))
    orch.register(_node("discord-node", channels=["discord"]))
    node = orch.select(_task(channel="slack"))
    assert node.name == "slack-node"


def test_orchestrator_channel_glob_routing() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("slack-any", channels=["slack*"]))
    node = orch.select(_task(channel="slack-enterprise"))
    assert node.name == "slack-any"


def test_orchestrator_combined_routing() -> None:
    orch = AgentOrchestrator()
    orch.register(_node(
        "precise",
        task_types=["code_generation"],
        keywords=["python"],
        channels=["slack"],
        priority=20,
    ))
    orch.register(_node("fallback"))
    node = orch.select(_task(content="python code", task_type="code_generation", channel="slack"))
    assert node.name == "precise"


# ---------------------------------------------------------------------------
# AgentOrchestrator — async route()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_route_returns_result() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("alpha"))
    result = await orch.route(_task())
    assert isinstance(result, AgentResult)
    assert result.node_name == "alpha"


@pytest.mark.asyncio
async def test_orchestrator_route_no_node_raises() -> None:
    orch = AgentOrchestrator()
    with pytest.raises(NoEligibleNodeError):
        await orch.route(_task())


@pytest.mark.asyncio
async def test_orchestrator_route_updates_stats() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("n"))
    await orch.route(_task())
    assert orch.stats()["total_routed"] == 1


@pytest.mark.asyncio
async def test_orchestrator_route_increments_node_tasks_handled() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("n"))
    await orch.route(_task())
    assert orch.get("n").stats()["tasks_handled"] == 1


@pytest.mark.asyncio
async def test_orchestrator_route_result_has_model_override() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("n", model="anthropic/claude-sonnet-5"))
    result = await orch.route(_task())
    assert result.metadata["model_override"] == "anthropic/claude-sonnet-5"


@pytest.mark.asyncio
async def test_orchestrator_route_result_model_override_none_by_default() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("n"))
    result = await orch.route(_task())
    assert result.metadata["model_override"] is None


# ---------------------------------------------------------------------------
# AgentOrchestrator — stats()
# ---------------------------------------------------------------------------


def test_orchestrator_stats_initial() -> None:
    orch = AgentOrchestrator()
    s = orch.stats()
    assert s["total_routed"] == 0
    assert s["node_count"] == 0
    assert s["has_fallback"] is False


def test_orchestrator_stats_with_fallback() -> None:
    orch = AgentOrchestrator(fallback_config=_node("fb"))
    assert orch.stats()["has_fallback"] is True


def test_orchestrator_stats_node_list() -> None:
    orch = AgentOrchestrator()
    orch.register(_node("a"))
    orch.register(_node("b"))
    s = orch.stats()
    assert len(s["nodes"]) == 2


# ---------------------------------------------------------------------------
# REST routes
# ---------------------------------------------------------------------------


def test_routes_list_nodes_empty() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.get("/api/v1/orchestrator/nodes")
    assert resp.status_code == 200
    assert resp.json()["nodes"] == []


def test_routes_list_nodes_with_data() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    orch.register(_node("n1"))
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.get("/api/v1/orchestrator/nodes")
    assert any(n["name"] == "n1" for n in resp.json()["nodes"])


def test_routes_register_node() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.post("/api/v1/orchestrator/nodes", json={"name": "coder", "priority": 5})
    assert resp.status_code == 201
    assert resp.json()["node"]["name"] == "coder"


def test_routes_register_invalid_node() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.post("/api/v1/orchestrator/nodes", json={"name": "bad name!"})
    assert resp.status_code == 422


def test_routes_get_node() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    orch.register(_node("alpha"))
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.get("/api/v1/orchestrator/nodes/alpha")
    assert resp.status_code == 200
    assert resp.json()["name"] == "alpha"


def test_routes_get_node_not_found() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    set_orchestrator(AgentOrchestrator())
    client = TestClient(app)
    resp = client.get("/api/v1/orchestrator/nodes/ghost")
    assert resp.status_code == 404


def test_routes_delete_node() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    orch.register(_node("del-me"))
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.delete("/api/v1/orchestrator/nodes/del-me")
    assert resp.status_code == 204
    assert orch.node_count() == 0


def test_routes_delete_node_not_found() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    set_orchestrator(AgentOrchestrator())
    client = TestClient(app)
    resp = client.delete("/api/v1/orchestrator/nodes/ghost")
    assert resp.status_code == 404


def test_routes_patch_node_enable_disable() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    orch.register(_node("patchme"))
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.patch("/api/v1/orchestrator/nodes/patchme", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["node"]["enabled"] is False


def test_routes_route_task() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    orch.register(_node("worker"))
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.post("/api/v1/orchestrator/route", json={"content": "do work"})
    assert resp.status_code == 200
    assert resp.json()["node_name"] == "worker"


def test_routes_route_task_no_eligible() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    orch.register(_node("coder", task_types=["code_generation"]))
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.post("/api/v1/orchestrator/route",
                       json={"content": "summarize this", "task_type": "summarization"})
    assert resp.status_code == 422


def test_routes_route_task_empty_content() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    set_orchestrator(AgentOrchestrator())
    client = TestClient(app)
    resp = client.post("/api/v1/orchestrator/route", json={"content": ""})
    assert resp.status_code == 422


def test_routes_status() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    orch = AgentOrchestrator()
    orch.register(_node("n"))
    set_orchestrator(orch)
    client = TestClient(app)
    resp = client.get("/api/v1/orchestrator/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["node_count"] == 1


def test_routes_status_no_orchestrator() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    set_orchestrator(None)
    client = TestClient(app)
    resp = client.get("/api/v1/orchestrator/status")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_routes_list_nodes_no_orchestrator() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    set_orchestrator(None)
    client = TestClient(app)
    resp = client.get("/api/v1/orchestrator/nodes")
    assert resp.status_code == 200
    assert resp.json()["nodes"] == []


def test_routes_register_node_no_orchestrator() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cortexflow_ai.gateway.routes import router, set_orchestrator

    app = FastAPI()
    app.include_router(router)
    set_orchestrator(None)
    client = TestClient(app)
    resp = client.post("/api/v1/orchestrator/nodes", json={"name": "x"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_orchestrate_list_empty() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["orchestrate", "list"])
    assert result.exit_code == 0
    assert "No nodes" in result.output


def test_cli_orchestrate_add() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["orchestrate", "add", "--name", "coder",
                                  "--task-types", "code_generation",
                                  "--priority", "5"])
    assert result.exit_code == 0
    assert "coder" in result.output


def test_cli_orchestrate_add_invalid_name() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["orchestrate", "add", "--name", "bad name!"])
    assert result.exit_code != 0 or "Invalid" in result.output


def test_cli_orchestrate_remove_missing() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["orchestrate", "remove", "ghost"])
    assert result.exit_code != 0 or "not found" in result.output.lower()


def test_cli_orchestrate_status_empty() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["orchestrate", "status"])
    assert result.exit_code == 0
    assert "Total routed" in result.output or "routed" in result.output.lower()


def test_cli_orchestrate_route_no_nodes() -> None:
    from cortexflow_ai.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["orchestrate", "route", "--content", "hello"])
    assert result.exit_code != 0 or "No eligible" in result.output
