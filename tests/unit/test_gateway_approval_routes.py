"""Tests for /api/v1/approvals gateway routes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from neuralcleave.gateway.main import create_app
from neuralcleave.gateway.routes import set_runtime
from neuralcleave.tools.approval_policy import POLICY
from neuralcleave.tools.approvals import APPROVAL_QUEUE


@pytest.fixture(autouse=True)
def clear_runtime():
    set_runtime(None)
    yield
    set_runtime(None)


@pytest.fixture(autouse=True)
def clear_queue():
    """Clear the global queue before each test."""
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)
    yield
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)


@pytest.fixture(autouse=True)
def clear_policy():
    """Reset the global allowlist policy's entries and modes around each test."""
    original_security, original_ask = POLICY.security, POLICY.ask
    POLICY._entries.clear()
    yield
    POLICY._entries.clear()
    POLICY.security, POLICY.ask = original_security, original_ask


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

    def test_approve_without_always_reports_always_allowed_false(self, client: TestClient) -> None:
        req = APPROVAL_QUEUE.request("shell", "git status", {}, session_id="s")
        resp = client.post(f"/api/v1/approvals/{req.id}/approve")
        assert resp.json()["always_allowed"] is False
        assert POLICY.list_entries() == []

    def test_approve_with_always_persists_an_allowlist_entry(self, client: TestClient) -> None:
        req = APPROVAL_QUEUE.request("shell", "git status", {}, session_id="s")
        resp = client.post(f"/api/v1/approvals/{req.id}/approve", json={"always": True})
        assert resp.json()["always_allowed"] is True
        entries = POLICY.list_entries()
        assert len(entries) == 1
        assert entries[0].pattern == "git"


class TestAllowlistRoutes:
    def test_list_empty_when_no_entries(self, client: TestClient) -> None:
        resp = client.get("/api/v1/approvals/allowlist")
        assert resp.status_code == 200
        assert resp.json()["entries"] == []

    def test_add_entry(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/allowlist", json={"pattern": "git"})
        assert resp.status_code == 200
        assert resp.json()["entry"]["pattern"] == "git"

    def test_add_entry_missing_pattern_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/allowlist", json={})
        assert resp.status_code == 422

    def test_add_entry_with_arg_pattern(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/approvals/allowlist", json={"pattern": "git", "arg_pattern": "^git log"}
        )
        assert resp.json()["entry"]["arg_pattern"] == "^git log"

    def test_list_reflects_added_entry(self, client: TestClient) -> None:
        client.post("/api/v1/approvals/allowlist", json={"pattern": "curl"})
        resp = client.get("/api/v1/approvals/allowlist")
        assert len(resp.json()["entries"]) == 1

    def test_remove_entry(self, client: TestClient) -> None:
        add_resp = client.post("/api/v1/approvals/allowlist", json={"pattern": "git"})
        entry_id = add_resp.json()["entry"]["id"]
        resp = client.delete(f"/api/v1/approvals/allowlist/{entry_id}")
        assert resp.status_code == 200
        assert resp.json()["removed"] is True
        assert POLICY.list_entries() == []

    def test_remove_unknown_entry_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/approvals/allowlist/999999")
        assert resp.status_code == 404


class TestApprovalPolicyRoutes:
    def test_get_returns_current_modes(self, client: TestClient) -> None:
        resp = client.get("/api/v1/approvals/policy")
        assert resp.status_code == 200
        body = resp.json()
        assert "security" in body
        assert "ask" in body

    def test_get_require_shell_approval_is_none_without_a_runtime(self, client: TestClient) -> None:
        resp = client.get("/api/v1/approvals/policy")
        assert resp.json()["require_shell_approval"] is None

    def test_get_require_shell_approval_reflects_the_live_shell_tool(self, client: TestClient) -> None:
        """Round 4 (2026-08-21 gap analysis) P0 follow-up: the security/ask
        modes are meaningless if the gate itself isn't enabled on the live
        ShellTool — this makes that reachable via the same route."""
        shell_tool = MagicMock()
        shell_tool._require_approval = True
        runtime = MagicMock()
        runtime._pipeline._tool_registry.get.return_value = shell_tool
        set_runtime(runtime)

        resp = client.get("/api/v1/approvals/policy")

        assert resp.json()["require_shell_approval"] is True
        runtime._pipeline._tool_registry.get.assert_called_once_with("shell")

    def test_post_updates_security_mode(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/policy", json={"security": "full"})
        assert resp.status_code == 200
        assert resp.json()["security"] == "full"
        assert POLICY.security == "full"

    def test_post_updates_ask_mode(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/policy", json={"ask": "always"})
        assert resp.status_code == 200
        assert resp.json()["ask"] == "always"

    def test_post_invalid_security_mode_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/policy", json={"security": "nope"})
        assert resp.status_code == 422

    def test_post_invalid_ask_mode_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/policy", json={"ask": "nope"})
        assert resp.status_code == 422

    def test_post_omitted_key_leaves_that_mode_unchanged(self, client: TestClient) -> None:
        client.post("/api/v1/approvals/policy", json={"security": "deny"})
        resp = client.post("/api/v1/approvals/policy", json={"ask": "off"})
        assert resp.json()["security"] == "deny"
        assert resp.json()["ask"] == "off"

    def test_post_require_shell_approval_toggles_the_live_shell_and_browser_tools(
        self, client: TestClient
    ) -> None:
        shell_tool = MagicMock(_require_approval=False)
        browser_tool = MagicMock(_require_approval=False)
        runtime = MagicMock()
        runtime._pipeline._tool_registry.get.side_effect = (
            lambda name: {"shell": shell_tool, "browser": browser_tool}.get(name)
        )
        set_runtime(runtime)

        resp = client.post("/api/v1/approvals/policy", json={"require_shell_approval": True})

        assert resp.status_code == 200
        assert resp.json()["require_shell_approval"] is True
        assert shell_tool._require_approval is True
        assert browser_tool._require_approval is True

    def test_post_require_shell_approval_non_bool_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/approvals/policy", json={"require_shell_approval": "yes"})
        assert resp.status_code == 422

    def test_post_require_shell_approval_without_a_runtime_does_not_raise(
        self, client: TestClient
    ) -> None:
        resp = client.post("/api/v1/approvals/policy", json={"require_shell_approval": True})
        assert resp.status_code == 200
        assert resp.json()["require_shell_approval"] is None
