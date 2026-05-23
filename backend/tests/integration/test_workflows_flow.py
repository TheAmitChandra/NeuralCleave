"""
Integration tests — Workflows API (/api/v1/workflows/*)

Covers:
  POST  /api/v1/workflows/run              — create and start a workflow
  GET   /api/v1/workflows/                 — list workflows (scoped to owner)
  GET   /api/v1/workflows/{id}             — get single workflow
  POST  /api/v1/workflows/{id}/pause       — pause a running workflow
  POST  /api/v1/workflows/{id}/resume      — resume a paused workflow
  POST  /api/v1/workflows/{id}/rollback    — rollback a failed workflow

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
    email = f"wftest{suffix}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": "WF Tester"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecureP@ss123"},
    )
    return resp.json()["access_token"]


async def _run_workflow(
    client: AsyncClient,
    token: str,
    name: str = "TestWorkflow",
    trigger_source: str = "manual",
) -> dict:
    resp = await client.post(
        "/api/v1/workflows/run",
        json={"name": name, "trigger_source": trigger_source},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_workflow_success(client: AsyncClient) -> None:
    token = await _register_and_login(client, "run")
    resp = await client.post(
        "/api/v1/workflows/run",
        json={"name": "DataPipeline", "trigger_source": "manual"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "DataPipeline"
    assert data["status"] == "RUNNING"
    assert data["trigger_source"] == "manual"
    assert "workflow_id" in data


@pytest.mark.anyio
async def test_run_workflow_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/workflows/run",
        json={"name": "Unauthorized"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_workflows_empty(client: AsyncClient) -> None:
    token = await _register_and_login(client, "listempty")
    resp = await client.get(
        "/api/v1/workflows/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_workflows_returns_own_only(client: AsyncClient) -> None:
    token_a = await _register_and_login(client, "owna")
    token_b = await _register_and_login(client, "ownb")

    await _run_workflow(client, token_a, "WorkflowA")
    await _run_workflow(client, token_b, "WorkflowB")

    resp_a = await client.get(
        "/api/v1/workflows/", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp_a.status_code == 200
    names = [w["name"] for w in resp_a.json()]
    assert "WorkflowA" in names
    assert "WorkflowB" not in names


@pytest.mark.anyio
async def test_get_workflow_by_id(client: AsyncClient) -> None:
    token = await _register_and_login(client, "getbyid")
    created = await _run_workflow(client, token, "GetByIdWF")
    wf_id = created["workflow_id"]

    resp = await client.get(
        f"/api/v1/workflows/{wf_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["workflow_id"] == wf_id
    assert resp.json()["name"] == "GetByIdWF"


@pytest.mark.anyio
async def test_get_workflow_not_found(client: AsyncClient) -> None:
    token = await _register_and_login(client, "notfound")
    resp = await client.get(
        f"/api/v1/workflows/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_pause_workflow(client: AsyncClient) -> None:
    token = await _register_and_login(client, "pause")
    created = await _run_workflow(client, token, "PauseWF")
    wf_id = created["workflow_id"]

    resp = await client.post(
        f"/api/v1/workflows/{wf_id}/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "pause"
    assert data["status"] == "PAUSED"


@pytest.mark.anyio
async def test_resume_paused_workflow(client: AsyncClient) -> None:
    token = await _register_and_login(client, "resume")
    created = await _run_workflow(client, token, "ResumeWF")
    wf_id = created["workflow_id"]

    # Pause first
    await client.post(
        f"/api/v1/workflows/{wf_id}/pause",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Now resume
    resp = await client.post(
        f"/api/v1/workflows/{wf_id}/resume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "resume"
    assert data["status"] == "RUNNING"


@pytest.mark.anyio
async def test_rollback_workflow(client: AsyncClient) -> None:
    token = await _register_and_login(client, "rollback")
    created = await _run_workflow(client, token, "RollbackWF")
    wf_id = created["workflow_id"]

    resp = await client.post(
        f"/api/v1/workflows/{wf_id}/rollback",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "rollback"
    assert data["status"] == "ROLLED_BACK"


@pytest.mark.anyio
async def test_run_workflow_with_dag_definition(client: AsyncClient) -> None:
    token = await _register_and_login(client, "dag")
    dag = {
        "nodes": [
            {"id": "step1", "type": "research", "label": "Gather data"},
            {"id": "step2", "type": "analysis", "label": "Analyze results"},
        ],
        "edges": [{"source": "step1", "target": "step2"}],
    }
    resp = await client.post(
        "/api/v1/workflows/run",
        json={"name": "DAGWorkflow", "dag_definition": dag, "trigger_source": "api"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["dag_definition"] == dag
    assert data["trigger_source"] == "api"


@pytest.mark.anyio
async def test_workflow_action_not_found(client: AsyncClient) -> None:
    token = await _register_and_login(client, "actionnotfound")
    resp = await client.post(
        f"/api/v1/workflows/{uuid.uuid4()}/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
