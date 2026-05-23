"""Unit tests for the approvals REST API router.

Covers:
    - GET  /approvals/pending  — list PENDING requests
    - GET  /approvals/         — list all requests
    - GET  /approvals/{id}     — get one request (200 + 404)
    - POST /approvals/{id}/approve  — approve (200 + 400 non-pending)
    - POST /approvals/{id}/reject   — reject with reason (200 + 400)
    - POST /approvals/{id}/cancel   — cancel by actor (200 + 400 wrong actor)
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.approvals import router, _workflow
from app.core.governance.approvals import (
    ApprovalPriority,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStore,
    ApprovalWorkflow,
)
from app.db.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_user(user_id: str = "operator-001") -> User:
    u = MagicMock(spec=User)
    u.id = user_id
    return u


def _make_app(fake_store: ApprovalStore) -> tuple[FastAPI, TestClient]:
    """Build a minimal FastAPI app with the approvals router + faked deps."""
    from app.core.security.permission_engine import get_current_user
    from app.db.postgres import get_db

    app = FastAPI()
    app.include_router(router)  # router already carries prefix="/approvals"

    async def _fake_user_dep():
        return _fake_user()

    async def _fake_db():
        yield MagicMock()

    app.dependency_overrides[get_current_user] = _fake_user_dep
    app.dependency_overrides[get_db] = _fake_db

    return app, TestClient(app, raise_server_exceptions=False)


def _seed_request(
    store: ApprovalStore,
    *,
    status: ApprovalStatus = ApprovalStatus.PENDING,
    actor_id: str = "agent-abc",
    risk_score: int = 90,
) -> ApprovalRequest:
    """Synchronously seed an ApprovalRequest into the store."""
    import asyncio

    from datetime import datetime, timedelta, timezone

    req = ApprovalRequest(
        request_id=str(uuid.uuid4()),
        actor_id=actor_id,
        tool_name="shell.execute",
        tool_params={"command": "rm -rf /tmp/test"},
        action_description="Delete temp directory",
        risk_score=risk_score,
        priority=ApprovalPriority.CRITICAL,
        status=status,
        tenant_id="default",
        created_at=datetime.now(tz=timezone.utc),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )

    asyncio.get_event_loop().run_until_complete(store.save(req))
    return req


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def isolated_workflow(monkeypatch):
    """Replace the module-level _workflow singleton with a fresh instance."""
    fresh_store = ApprovalStore()
    fresh_workflow = ApprovalWorkflow(store=fresh_store)

    import app.api.v1.approvals as approvals_mod

    monkeypatch.setattr(approvals_mod, "_workflow", fresh_workflow)
    yield fresh_workflow, fresh_store


@pytest.fixture()
def client(isolated_workflow):
    """TestClient against a fresh app with isolated workflow."""
    _, store = isolated_workflow
    _, tc = _make_app(store)
    return tc


@pytest.fixture()
def pending_req(isolated_workflow):
    """A single PENDING request seeded in the store."""
    _, store = isolated_workflow
    return _seed_request(store)


# ===========================================================================
# GET /approvals/pending
# ===========================================================================

class TestListPending:

    def test_empty_queue_returns_empty_list(self, client: TestClient):
        res = client.get("/approvals/pending")
        assert res.status_code == 200
        assert res.json() == []

    def test_returns_only_pending(self, client: TestClient, isolated_workflow):
        _, store = isolated_workflow
        pending = _seed_request(store, status=ApprovalStatus.PENDING)
        _seed_request(store, status=ApprovalStatus.APPROVED)

        res = client.get("/approvals/pending")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["request_id"] == pending.request_id
        assert data[0]["status"] == "PENDING"


# ===========================================================================
# GET /approvals/
# ===========================================================================

class TestListAll:

    def test_empty_returns_list(self, client: TestClient):
        res = client.get("/approvals/")
        assert res.status_code == 200
        assert res.json() == []

    def test_returns_all_statuses(self, client: TestClient, isolated_workflow):
        _, store = isolated_workflow
        _seed_request(store, status=ApprovalStatus.PENDING)
        _seed_request(store, status=ApprovalStatus.APPROVED)
        _seed_request(store, status=ApprovalStatus.REJECTED)

        res = client.get("/approvals/")
        assert res.status_code == 200
        assert len(res.json()) == 3


# ===========================================================================
# GET /approvals/{id}
# ===========================================================================

class TestGetApproval:

    def test_returns_request(self, client: TestClient, pending_req: ApprovalRequest):
        res = client.get(f"/approvals/{pending_req.request_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["request_id"] == pending_req.request_id
        assert body["tool_name"] == "shell.execute"
        assert body["risk_score"] == 90

    def test_404_for_unknown_id(self, client: TestClient):
        res = client.get(f"/approvals/{uuid.uuid4()}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


# ===========================================================================
# POST /approvals/{id}/approve
# ===========================================================================

class TestApprove:

    def test_approve_pending_returns_approved(self, client: TestClient, pending_req: ApprovalRequest):
        res = client.post(f"/approvals/{pending_req.request_id}/approve")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "APPROVED"
        assert body["decided_by"] is not None

    def test_approve_nonexistent_returns_404(self, client: TestClient):
        res = client.post(f"/approvals/{uuid.uuid4()}/approve")
        assert res.status_code == 404

    def test_double_approve_returns_400(self, client: TestClient, pending_req: ApprovalRequest):
        client.post(f"/approvals/{pending_req.request_id}/approve")
        res = client.post(f"/approvals/{pending_req.request_id}/approve")
        assert res.status_code == 400


# ===========================================================================
# POST /approvals/{id}/reject
# ===========================================================================

class TestReject:

    def test_reject_pending_returns_rejected(self, client: TestClient, pending_req: ApprovalRequest):
        res = client.post(
            f"/approvals/{pending_req.request_id}/reject",
            json={"reason": "Too dangerous"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "REJECTED"
        assert "Too dangerous" in (body["rejection_reason"] or "")

    def test_reject_without_reason_uses_empty_string(self, client: TestClient, pending_req: ApprovalRequest):
        res = client.post(
            f"/approvals/{pending_req.request_id}/reject",
            json={"reason": ""},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "REJECTED"

    def test_reject_nonexistent_returns_404(self, client: TestClient):
        res = client.post(f"/approvals/{uuid.uuid4()}/reject", json={"reason": ""})
        assert res.status_code == 404

    def test_double_reject_returns_400(self, client: TestClient, pending_req: ApprovalRequest):
        client.post(f"/approvals/{pending_req.request_id}/reject", json={"reason": "x"})
        res = client.post(f"/approvals/{pending_req.request_id}/reject", json={"reason": "x"})
        assert res.status_code == 400


# ===========================================================================
# POST /approvals/{id}/cancel
# ===========================================================================

class TestCancel:

    def test_cancel_by_originator_returns_cancelled(self, client: TestClient, isolated_workflow):
        _, store = isolated_workflow
        req = _seed_request(store, actor_id="agent-xyz")
        res = client.post(
            f"/approvals/{req.request_id}/cancel",
            json={"actor_id": "agent-xyz"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "CANCELLED"

    def test_cancel_by_wrong_actor_returns_400(self, client: TestClient, isolated_workflow):
        _, store = isolated_workflow
        req = _seed_request(store, actor_id="agent-xyz")
        res = client.post(
            f"/approvals/{req.request_id}/cancel",
            json={"actor_id": "different-agent"},
        )
        assert res.status_code == 400

    def test_cancel_nonexistent_returns_404(self, client: TestClient):
        res = client.post(
            f"/approvals/{uuid.uuid4()}/cancel",
            json={"actor_id": "agent-xyz"},
        )
        assert res.status_code == 404
