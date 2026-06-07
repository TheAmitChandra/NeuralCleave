"""Unit tests for the workflow DAG update endpoint.

Covers PATCH /workflows/{id}/dag:
    - 200 success — dag_definition persisted
    - 200 empty dag_definition accepted
    - 200 response includes full WorkflowResponse schema
    - 404 not found (mocked _get_workflow_or_404 raising HTTPException)
    - 422 invalid UUID in path
    - 422 missing dag_definition field in body
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.workflows import router
from app.db.models.user import User
from app.db.models.workflow import Workflow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OWNER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _fake_user() -> User:
    u = MagicMock(spec=User)
    u.id = _OWNER_UUID
    return u


def _fake_workflow(workflow_id: str) -> Workflow:
    wf = MagicMock(spec=Workflow)
    wf.id = uuid.UUID(workflow_id)
    wf.owner_id = _OWNER_UUID
    wf.name = "Test Workflow"
    wf.status = "RUNNING"
    wf.dag_definition = {}
    wf.version = 1
    wf.agent_id = None
    wf.trigger_source = "manual"
    wf.created_at = datetime.now(timezone.utc)
    return wf


def _make_app() -> tuple[FastAPI, TestClient]:
    from app.core.security.permission_engine import get_current_user
    from app.db.postgres import get_db

    app = FastAPI()
    app.include_router(router)  # router carries prefix="/workflows"

    async def _user_dep():
        return _fake_user()

    async def _db_dep():
        session = AsyncMock()
        session.flush = AsyncMock()
        yield session

    app.dependency_overrides[get_current_user] = _user_dep
    app.dependency_overrides[get_db] = _db_dep
    return app, TestClient(app, raise_server_exceptions=False)


_SAMPLE_DAG: dict[str, Any] = {
    "nodes": [
        {
            "id": "wf-1",
            "data": {"label": "Start", "nodeType": "start"},
            "position": {"x": 60, "y": 120},
        },
        {
            "id": "wf-2",
            "data": {"label": "Process", "nodeType": "task"},
            "position": {"x": 260, "y": 120},
        },
    ],
    "edges": [{"id": "e1-2", "source": "wf-1", "target": "wf-2", "animated": True}],
}


# ===========================================================================
# Tests
# ===========================================================================


class TestUpdateDag:
    WF_ID = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Success paths
    # ------------------------------------------------------------------

    def test_success_returns_200_with_workflow_response(self, monkeypatch):
        _app, client = _make_app()
        wf = _fake_workflow(self.WF_ID)

        async def _mock_get(*_a, **_kw):
            return wf

        monkeypatch.setattr("app.api.v1.workflows._get_workflow_or_404", _mock_get)

        resp = client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={"dag_definition": _SAMPLE_DAG},
        )

        assert resp.status_code == 200

    def test_success_persists_dag_definition_on_model(self, monkeypatch):
        _app, client = _make_app()
        wf = _fake_workflow(self.WF_ID)

        async def _mock_get(*_a, **_kw):
            return wf

        monkeypatch.setattr("app.api.v1.workflows._get_workflow_or_404", _mock_get)

        client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={"dag_definition": _SAMPLE_DAG},
        )

        assert wf.dag_definition == _SAMPLE_DAG

    def test_success_response_contains_required_schema_fields(self, monkeypatch):
        _app, client = _make_app()
        wf = _fake_workflow(self.WF_ID)

        async def _mock_get(*_a, **_kw):
            return wf

        monkeypatch.setattr("app.api.v1.workflows._get_workflow_or_404", _mock_get)

        resp = client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={"dag_definition": _SAMPLE_DAG},
        )

        body = resp.json()
        for field in ("workflow_id", "name", "status", "version", "owner_id", "dag_definition"):
            assert field in body, f"missing field: {field}"

    def test_success_empty_dag_definition_accepted(self, monkeypatch):
        _app, client = _make_app()
        wf = _fake_workflow(self.WF_ID)

        async def _mock_get(*_a, **_kw):
            return wf

        monkeypatch.setattr("app.api.v1.workflows._get_workflow_or_404", _mock_get)

        resp = client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={"dag_definition": {}},
        )

        assert resp.status_code == 200
        assert wf.dag_definition == {}

    def test_success_response_workflow_id_matches_path(self, monkeypatch):
        _app, client = _make_app()
        wf = _fake_workflow(self.WF_ID)

        async def _mock_get(*_a, **_kw):
            return wf

        monkeypatch.setattr("app.api.v1.workflows._get_workflow_or_404", _mock_get)

        resp = client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={"dag_definition": _SAMPLE_DAG},
        )

        assert resp.json()["workflow_id"] == self.WF_ID

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_not_found_returns_404(self, monkeypatch):
        from fastapi import HTTPException
        from fastapi import status as http_status

        _app, client = _make_app()

        async def _mock_get(*_a, **_kw):
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Workflow not found",
            )

        monkeypatch.setattr("app.api.v1.workflows._get_workflow_or_404", _mock_get)

        resp = client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={"dag_definition": _SAMPLE_DAG},
        )

        assert resp.status_code == 404

    def test_invalid_uuid_in_path_returns_422(self):
        _app, client = _make_app()

        resp = client.patch(
            "/workflows/not-a-valid-uuid/dag",
            json={"dag_definition": _SAMPLE_DAG},
        )

        assert resp.status_code == 422

    def test_missing_dag_definition_field_returns_422(self):
        _app, client = _make_app()

        resp = client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={},  # dag_definition is required
        )

        assert resp.status_code == 422

    def test_wrong_owner_returns_404(self, monkeypatch):
        """Simulates _get_workflow_or_404 returning 404 for a different owner."""
        from fastapi import HTTPException
        from fastapi import status as http_status

        _app, client = _make_app()

        async def _mock_get(*_a, **_kw):
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Workflow not found",
            )

        monkeypatch.setattr("app.api.v1.workflows._get_workflow_or_404", _mock_get)

        resp = client.patch(
            f"/workflows/{self.WF_ID}/dag",
            json={"dag_definition": _SAMPLE_DAG},
        )

        assert resp.status_code == 404
