"""
Integration tests — Agents API (/api/v1/agents/*)

Covers:
  POST   /api/v1/agents/create          — create a new agent
  GET    /api/v1/agents/                — list agents (scoped to owner)
  GET    /api/v1/agents/{id}            — get single agent
  PATCH  /api/v1/agents/{id}/status     — update agent status
  POST   /api/v1/agents/{id}/execute    — dispatch execution task
  DELETE /api/v1/agents/{id}            — delete agent

All tests use a real PostgreSQL session (rolled back after each test).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client: AsyncClient, suffix: str = "") -> str:
    """Register a user and return an access token."""
    email = f"agenttest{suffix}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": "Agent Tester"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecureP@ss123"},
    )
    return resp.json()["access_token"]


async def _create_agent(client: AsyncClient, token: str, name: str = "TestAgent") -> dict:
    resp = await client.post(
        "/api/v1/agents/create",
        json={"name": name, "agent_type": "generic"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_agent_success(client: AsyncClient) -> None:
    token = await _register_and_login(client, "create")
    resp = await client.post(
        "/api/v1/agents/create",
        json={"name": "MyAgent", "agent_type": "planner"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "MyAgent"
    assert data["agent_type"] == "planner"
    assert data["status"] == "IDLE"
    assert "agent_id" in data


@pytest.mark.anyio
async def test_create_agent_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/agents/create",
        json={"name": "Unauthorized", "agent_type": "generic"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_agents_empty(client: AsyncClient) -> None:
    token = await _register_and_login(client, "listempty")
    resp = await client.get(
        "/api/v1/agents/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_agents_returns_own_agents_only(client: AsyncClient) -> None:
    token_a = await _register_and_login(client, "lista")
    token_b = await _register_and_login(client, "listb")

    await _create_agent(client, token_a, "AgentOwnerA")
    await _create_agent(client, token_b, "AgentOwnerB")

    resp_a = await client.get("/api/v1/agents/", headers={"Authorization": f"Bearer {token_a}"})
    assert resp_a.status_code == 200
    names_a = [a["name"] for a in resp_a.json()]
    assert "AgentOwnerA" in names_a
    assert "AgentOwnerB" not in names_a


@pytest.mark.anyio
async def test_get_agent_by_id(client: AsyncClient) -> None:
    token = await _register_and_login(client, "getbyid")
    created = await _create_agent(client, token, "ByIdAgent")
    agent_id = created["agent_id"]

    resp = await client.get(
        f"/api/v1/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == agent_id
    assert resp.json()["name"] == "ByIdAgent"


@pytest.mark.anyio
async def test_get_agent_not_found(client: AsyncClient) -> None:
    token = await _register_and_login(client, "getnotfound")
    import uuid
    resp = await client.get(
        f"/api/v1/agents/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_get_agent_invalid_uuid(client: AsyncClient) -> None:
    token = await _register_and_login(client, "invaliduuid")
    resp = await client.get(
        "/api/v1/agents/not-a-uuid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_agent_status_to_paused(client: AsyncClient) -> None:
    token = await _register_and_login(client, "statuspause")
    created = await _create_agent(client, token)
    agent_id = created["agent_id"]

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/status",
        json={"status": "PAUSED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "PAUSED"


@pytest.mark.anyio
async def test_update_agent_status_to_terminated(client: AsyncClient) -> None:
    token = await _register_and_login(client, "statusterm")
    created = await _create_agent(client, token)
    agent_id = created["agent_id"]

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/status",
        json={"status": "TERMINATED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "TERMINATED"


@pytest.mark.anyio
async def test_update_agent_status_invalid_value(client: AsyncClient) -> None:
    token = await _register_and_login(client, "statusinvalid")
    created = await _create_agent(client, token)
    agent_id = created["agent_id"]

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/status",
        json={"status": "FLYING"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_execute_agent(client: AsyncClient) -> None:
    token = await _register_and_login(client, "execute")
    created = await _create_agent(client, token)
    agent_id = created["agent_id"]

    resp = await client.post(
        f"/api/v1/agents/{agent_id}/execute",
        json={"task": "Summarize the latest news about AI"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 202)
    data = resp.json()
    assert "task_id" in data or "status" in data


@pytest.mark.anyio
async def test_delete_agent(client: AsyncClient) -> None:
    token = await _register_and_login(client, "delete")
    created = await _create_agent(client, token)
    agent_id = created["agent_id"]

    del_resp = await client.delete(
        f"/api/v1/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


@pytest.mark.anyio
async def test_delete_agent_not_found(client: AsyncClient) -> None:
    token = await _register_and_login(client, "deletenotfound")
    import uuid
    resp = await client.delete(
        f"/api/v1/agents/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
