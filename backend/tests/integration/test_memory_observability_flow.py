"""
Integration tests — Memory & Observability APIs

Memory:
  GET    /api/v1/memory/search?q=      — search memory entries
  POST   /api/v1/memory/store          — store a new memory entry
  DELETE /api/v1/memory/{id}           — delete a memory entry

Observability:
  GET    /api/v1/observability/logs    — fetch structured logs
  GET    /api/v1/observability/metrics — fetch runtime metrics

All tests use a real PostgreSQL session (rolled back after each test).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient, suffix: str = "") -> str:
    email = f"memtest{suffix}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": "Mem Tester"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecureP@ss123"},
    )
    return resp.json()["access_token"]


async def _store_entry(
    client: AsyncClient,
    token: str,
    content: str = "Test memory entry",
    memory_type: str = "episodic",
) -> dict:
    resp = await client.post(
        "/api/v1/memory/store",
        json={"content": content, "memory_type": memory_type, "importance_score": 0.8},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Memory tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_store_memory_entry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "store")
    resp = await client.post(
        "/api/v1/memory/store",
        json={
            "content": "The capital of France is Paris.",
            "memory_type": "semantic",
            "importance_score": 0.9,
            "tags": ["geography", "facts"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["memory_type"] == "semantic"
    assert data["content"] == "The capital of France is Paris."
    assert data["importance_score"] == 0.9
    assert "memory_id" in data


@pytest.mark.anyio
async def test_store_memory_invalid_type(client: AsyncClient) -> None:
    token = await _register_and_login(client, "invalidtype")
    resp = await client.post(
        "/api/v1/memory/store",
        json={"content": "Some content", "memory_type": "imaginary_type"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_search_memory_empty_results(client: AsyncClient) -> None:
    token = await _register_and_login(client, "searchempty")
    resp = await client.get(
        "/api/v1/memory/search",
        params={"q": "xyznonexistentterm123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["total"] == 0
    assert data["query"] == "xyznonexistentterm123"


@pytest.mark.anyio
async def test_search_memory_finds_stored_entry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "searchfind")
    await _store_entry(client, token, content="CortexFlow uses Neo4j for knowledge graphs")

    resp = await client.get(
        "/api/v1/memory/search",
        params={"q": "Neo4j"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    contents = [r["content"] for r in data["results"]]
    assert any("Neo4j" in c for c in contents)


@pytest.mark.anyio
async def test_search_memory_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/memory/search", params={"q": "test"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_search_memory_filter_by_type(client: AsyncClient) -> None:
    token = await _register_and_login(client, "filtertype")
    await _store_entry(client, token, content="Episodic memory item", memory_type="episodic")
    await _store_entry(client, token, content="Semantic memory item", memory_type="semantic")

    resp = await client.get(
        "/api/v1/memory/search",
        params={"q": "memory", "memory_type": "episodic"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    for r in results:
        assert r["memory_type"] == "episodic"


@pytest.mark.anyio
async def test_delete_memory_entry(client: AsyncClient) -> None:
    token = await _register_and_login(client, "delete")
    stored = await _store_entry(client, token, content="Entry to delete")
    memory_id = stored["memory_id"]

    del_resp = await client.delete(
        f"/api/v1/memory/{memory_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204


@pytest.mark.anyio
async def test_delete_memory_not_found(client: AsyncClient) -> None:
    token = await _register_and_login(client, "deletenotfound")
    resp = await client.delete(
        f"/api/v1/memory/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Observability tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_metrics(client: AsyncClient) -> None:
    token = await _register_and_login(client, "metrics")
    resp = await client.get(
        "/api/v1/observability/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Metrics endpoint always returns these keys
    assert "tool_calls_total" in data
    assert "workflow_runs_total" in data
    assert "llm_requests_total" in data
    assert "active_agents" in data
    assert "snapshot" in data


@pytest.mark.anyio
async def test_get_metrics_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/observability/metrics")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_logs(client: AsyncClient) -> None:
    token = await _register_and_login(client, "logs")
    resp = await client.get(
        "/api/v1/observability/logs",
        params={"limit": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_get_logs_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/observability/logs")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_logs_level_filter(client: AsyncClient) -> None:
    token = await _register_and_login(client, "loglevel")
    resp = await client.get(
        "/api/v1/observability/logs",
        params={"min_level": "WARNING", "limit": 50},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    entries = resp.json()
    # All returned entries must be >= WARNING level
    for entry in entries:
        assert entry["level"] in ("WARNING", "ERROR", "CRITICAL")
