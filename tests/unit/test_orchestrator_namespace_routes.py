"""HTTP tests for orchestrator memory namespace REST endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cortexflow_ai.gateway import routes as routes_module
from cortexflow_ai.orchestrator import AgentOrchestrator
from cortexflow_ai.orchestrator.memory import MemoryNamespaceManager

# ---------------------------------------------------------------------------
# Test app and fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def orch():
    """A fresh orchestrator with an attached memory manager."""
    mgr = MemoryNamespaceManager()
    return AgentOrchestrator(memory_manager=mgr)


@pytest.fixture()
def app(orch):
    _app = FastAPI()
    _app.include_router(routes_module.router)
    with patch.object(routes_module, "_orchestrator", orch):
        yield _app


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def register_node(client, name, memory_namespace="", **extra):
    body = {"name": name, "memory_namespace": memory_namespace, **extra}
    return client.post("/api/v1/orchestrator/nodes", json=body)


# ---------------------------------------------------------------------------
# POST /api/v1/orchestrator/nodes — memory_namespace field
# ---------------------------------------------------------------------------


class TestRegisterNodeWithNamespace:
    def test_register_node_returns_201(self, client):
        r = register_node(client, "work")
        assert r.status_code == 201

    def test_register_node_response_has_memory_namespace(self, client):
        r = register_node(client, "work", "my-ns")
        assert r.json()["node"]["memory_namespace"] == "my-ns"

    def test_register_node_default_namespace_empty(self, client):
        r = register_node(client, "work")
        assert r.json()["node"]["memory_namespace"] == ""

    def test_register_node_effective_namespace_in_response(self, client):
        r = register_node(client, "work")
        assert r.json()["node"]["effective_memory_namespace"] == "work"

    def test_register_node_explicit_namespace_effective(self, client):
        r = register_node(client, "work", "pool")
        assert r.json()["node"]["effective_memory_namespace"] == "pool"


# ---------------------------------------------------------------------------
# GET /api/v1/orchestrator/nodes — list includes namespace
# ---------------------------------------------------------------------------


class TestListNodesNamespace:
    def test_list_nodes_includes_memory_namespace(self, client):
        register_node(client, "code", "dev")
        nodes = client.get("/api/v1/orchestrator/nodes").json()["nodes"]
        assert nodes[0]["memory_namespace"] == "dev"

    def test_list_nodes_includes_effective_namespace(self, client):
        register_node(client, "code")
        nodes = client.get("/api/v1/orchestrator/nodes").json()["nodes"]
        assert nodes[0]["effective_memory_namespace"] == "code"


# ---------------------------------------------------------------------------
# GET /api/v1/orchestrator/nodes/{name}/memory
# ---------------------------------------------------------------------------


class TestGetNodeMemoryEndpoint:
    def test_returns_200(self, client):
        register_node(client, "work")
        r = client.get("/api/v1/orchestrator/nodes/work/memory")
        assert r.status_code == 200

    def test_returns_node_field(self, client):
        register_node(client, "work")
        r = client.get("/api/v1/orchestrator/nodes/work/memory")
        assert r.json()["node"] == "work"

    def test_returns_memory_namespace(self, client):
        register_node(client, "work")
        r = client.get("/api/v1/orchestrator/nodes/work/memory")
        assert r.json()["memory_namespace"] == "work"

    def test_returns_configured_namespace(self, client):
        register_node(client, "work", "my-pool")
        r = client.get("/api/v1/orchestrator/nodes/work/memory")
        data = r.json()
        assert data["configured_namespace"] == "my-pool"
        assert data["memory_namespace"] == "my-pool"

    def test_returns_stats_field(self, client):
        register_node(client, "work")
        r = client.get("/api/v1/orchestrator/nodes/work/memory")
        assert "stats" in r.json()

    def test_unknown_node_returns_404(self, client):
        r = client.get("/api/v1/orchestrator/nodes/ghost/memory")
        assert r.status_code == 404

    def test_stats_none_when_namespace_not_yet_used(self, client):
        register_node(client, "work")
        r = client.get("/api/v1/orchestrator/nodes/work/memory")
        # Namespace store is lazily created; stats may be None if never accessed
        # via memory manager, or may have count=0 if created
        data = r.json()
        if data["stats"] is not None:
            assert data["stats"]["count"] >= 0

    def test_stats_populated_after_put(self, client, orch):
        register_node(client, "work")
        # Write directly into the orchestrator's memory manager
        orch._memory_manager.put("work", "k", "v")
        r = client.get("/api/v1/orchestrator/nodes/work/memory")
        assert r.json()["stats"]["count"] == 1


# ---------------------------------------------------------------------------
# DELETE /api/v1/orchestrator/nodes/{name}/memory
# ---------------------------------------------------------------------------


class TestClearNodeMemoryEndpoint:
    def test_returns_200(self, client):
        register_node(client, "work")
        r = client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert r.status_code == 200

    def test_response_has_node_field(self, client):
        register_node(client, "work")
        r = client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert r.json()["node"] == "work"

    def test_response_has_namespace_field(self, client):
        register_node(client, "work")
        r = client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert r.json()["namespace"] == "work"

    def test_response_has_cleared_count(self, client):
        register_node(client, "work")
        r = client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert "cleared" in r.json()

    def test_clears_zero_when_empty(self, client):
        register_node(client, "work")
        r = client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert r.json()["cleared"] == 0

    def test_clears_existing_entries(self, client, orch):
        register_node(client, "work")
        orch._memory_manager.put("work", "k1", "v")
        orch._memory_manager.put("work", "k2", "v")
        r = client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert r.json()["cleared"] == 2

    def test_after_clear_memory_empty(self, client, orch):
        register_node(client, "work")
        orch._memory_manager.put("work", "k", "v")
        client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert orch._memory_manager.namespace("work").count() == 0

    def test_unknown_node_returns_404(self, client):
        r = client.delete("/api/v1/orchestrator/nodes/ghost/memory")
        assert r.status_code == 404

    def test_clear_does_not_affect_other_namespace(self, client, orch):
        register_node(client, "work")
        register_node(client, "personal")
        orch._memory_manager.put("personal", "k", "v")
        client.delete("/api/v1/orchestrator/nodes/work/memory")
        assert orch._memory_manager.namespace("personal").count() == 1


# ---------------------------------------------------------------------------
# GET /api/v1/orchestrator/namespaces
# ---------------------------------------------------------------------------


class TestListNamespacesEndpoint:
    def test_returns_200(self, client):
        assert client.get("/api/v1/orchestrator/namespaces").status_code == 200

    def test_empty_orchestrator_returns_empty_map(self, client):
        r = client.get("/api/v1/orchestrator/namespaces")
        assert r.json()["namespaces"] == {}

    def test_registered_nodes_appear_in_map(self, client):
        register_node(client, "work")
        register_node(client, "personal")
        r = client.get("/api/v1/orchestrator/namespaces")
        ns_map = r.json()["namespaces"]
        assert "work" in ns_map
        assert "personal" in ns_map

    def test_namespace_values_correct(self, client):
        register_node(client, "code", "dev")
        r = client.get("/api/v1/orchestrator/namespaces")
        assert r.json()["namespaces"]["code"] == "dev"

    def test_has_memory_stats_field(self, client):
        r = client.get("/api/v1/orchestrator/namespaces")
        assert "memory_stats" in r.json()

    def test_memory_stats_structure(self, client, orch):
        register_node(client, "work")
        orch._memory_manager.put("work", "k", "v")
        r = client.get("/api/v1/orchestrator/namespaces")
        stats = r.json()["memory_stats"]
        assert "namespace_count" in stats
        assert "total_entries" in stats


# ---------------------------------------------------------------------------
# GET /api/v1/orchestrator/status — now includes namespaces
# ---------------------------------------------------------------------------


class TestOrchestratorStatusNamespaces:
    def test_status_includes_namespaces_key(self, client):
        r = client.get("/api/v1/orchestrator/status")
        assert "namespaces" in r.json()

    def test_status_namespaces_empty_initially(self, client):
        r = client.get("/api/v1/orchestrator/status")
        assert r.json()["namespaces"] == {}

    def test_status_namespaces_populated_after_register(self, client):
        register_node(client, "work")
        r = client.get("/api/v1/orchestrator/status")
        assert "work" in r.json()["namespaces"]


# ---------------------------------------------------------------------------
# Orchestrator unavailable (no _orchestrator set)
# ---------------------------------------------------------------------------


class TestOrchestratorUnavailable:
    @pytest.fixture()
    def no_orch_client(self):
        _app = FastAPI()
        _app.include_router(routes_module.router)
        with patch.object(routes_module, "_orchestrator", None):
            with TestClient(_app) as c:
                yield c

    def test_get_memory_503(self, no_orch_client):
        r = no_orch_client.get("/api/v1/orchestrator/nodes/x/memory")
        assert r.status_code == 503

    def test_delete_memory_503(self, no_orch_client):
        r = no_orch_client.delete("/api/v1/orchestrator/nodes/x/memory")
        assert r.status_code == 503

    def test_namespaces_returns_empty_when_unavailable(self, no_orch_client):
        r = no_orch_client.get("/api/v1/orchestrator/namespaces")
        assert r.status_code == 200
        assert r.json()["namespaces"] == {}
