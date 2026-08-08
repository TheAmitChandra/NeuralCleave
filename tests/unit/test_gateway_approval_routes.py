"""Tests for /api/v1/approvals gateway routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.main import create_app
from neuralcleave.tools.approvals import APPROVAL_QUEUE


@pytest.fixture(autouse=True)
def clear_queue():
    """Clear the global queue before each test."""
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)
    yield
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


class TestApprovalRoutes:
    def test_pending_empty_when_no_requests(self, client: TestClient) -> None:
        resp = client.get("/api/v1/approvals/pending")
        assert resp.status_code == 200
        assert resp.json()["pending"] == []

    def test_pending_lists_queued_request(self, client: TestClient) -> None:
        req = APPROVAL_QUEUE.request("shell", "ls -la", {}, session_id="s1")
        resp = client.get("/api/v1/approvals/pending")
        data = resp.json()
        assert len(data["pending"]) == 1
        assert data["pending"][0]["id"] == req.id

    def test_approve_returns_200_and_approved_true(self, client: TestClient) -> None:
        req = APPROVAL_QUEUE.request("shell", "git status", {}, session_id="s")
        resp = client.post(f"/api/v1/approvals/{req.id}/approve")
        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    def test_approve_removes_from_pending(self, client: TestClient) -> None:
        req = APPROVAL_QUEUE.request("shell", "echo hi", {}, session_id="s")
        client.post(f"/api/v1/approvals/{req.id}/approve")
        resp = client.get("/api/v1/approvals/pending")
        assert resp.json()["pending"] == []

    def test_approve_unknown_id_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/no-such-id/approve")
        assert resp.status_code == 404

    def test_deny_returns_200_and_denied_true(self, client: TestClient) -> None:
        req = APPROVAL_QUEUE.request("shell", "rm -rf /", {}, session_id="s")
        resp = client.post(f"/api/v1/approvals/{req.id}/deny")
        assert resp.status_code == 200
        assert resp.json()["denied"] is True

    def test_deny_removes_from_pending(self, client: TestClient) -> None:
        req = APPROVAL_QUEUE.request("shell", "echo deny-me", {}, session_id="s")
        client.post(f"/api/v1/approvals/{req.id}/deny")
        resp = client.get("/api/v1/approvals/pending")
        assert resp.json()["pending"] == []

    def test_deny_unknown_id_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/ghost/deny")
        assert resp.status_code == 404

    def test_pending_response_includes_command_field(self, client: TestClient) -> None:
        APPROVAL_QUEUE.request("shell", "docker ps", {}, session_id="s")
        resp = client.get("/api/v1/approvals/pending")
        item = resp.json()["pending"][0]
        assert item["command"] == "docker ps"
