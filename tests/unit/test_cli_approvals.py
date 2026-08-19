"""Tests for the `neuralcleave approvals` CLI command group."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from neuralcleave.cli import cli
from neuralcleave.tools.approval_policy import POLICY
from neuralcleave.tools.approvals import APPROVAL_QUEUE


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def clear_state():
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)
    POLICY._entries.clear()
    yield
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)
    POLICY._entries.clear()


class TestApprovalsPending:
    def test_empty_reports_none_pending(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["approvals", "pending"])
        assert result.exit_code == 0
        assert "No commands pending" in result.output

    def test_lists_pending_command(self, runner: CliRunner) -> None:
        APPROVAL_QUEUE.request("shell", "git status", {}, session_id="s1")
        result = runner.invoke(cli, ["approvals", "pending"])
        assert result.exit_code == 0
        assert "git status" in result.output


class TestApprovalsApprove:
    def test_approve_by_full_id(self, runner: CliRunner) -> None:
        req = APPROVAL_QUEUE.request("shell", "ls", {}, session_id="s")
        result = runner.invoke(cli, ["approvals", "approve", req.id])
        assert result.exit_code == 0
        assert "Approved" in result.output
        assert APPROVAL_QUEUE.get(req.id) is None

    def test_approve_unknown_id_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["approvals", "approve", "nonexistent"])
        assert result.exit_code != 0

    def test_approve_with_always_adds_allowlist_entry(self, runner: CliRunner) -> None:
        req = APPROVAL_QUEUE.request("shell", "git status", {}, session_id="s")
        result = runner.invoke(cli, ["approvals", "approve", req.id, "--always"])
        assert result.exit_code == 0
        entries = POLICY.list_entries()
        assert len(entries) == 1
        assert entries[0].pattern == "git"


class TestApprovalsDeny:
    def test_deny_by_full_id(self, runner: CliRunner) -> None:
        req = APPROVAL_QUEUE.request("shell", "rm -rf /", {}, session_id="s")
        result = runner.invoke(cli, ["approvals", "deny", req.id])
        assert result.exit_code == 0
        assert "Denied" in result.output
        assert APPROVAL_QUEUE.get(req.id) is None

    def test_deny_unknown_id_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["approvals", "deny", "nonexistent"])
        assert result.exit_code != 0


class TestApprovalsAllowlist:
    def test_list_empty_reports_empty(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["approvals", "allowlist", "list"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_add_and_list(self, runner: CliRunner) -> None:
        add_result = runner.invoke(cli, ["approvals", "allowlist", "add", "git"])
        assert add_result.exit_code == 0
        assert "git" in add_result.output

        list_result = runner.invoke(cli, ["approvals", "allowlist", "list"])
        assert "git" in list_result.output

    def test_add_with_arg_pattern(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli, ["approvals", "allowlist", "add", "git", "--arg-pattern", "^git log"]
        )
        assert result.exit_code == 0
        assert POLICY.list_entries()[0].arg_pattern == "^git log"

    def test_remove_entry(self, runner: CliRunner) -> None:
        entry = POLICY.add_entry("curl")
        result = runner.invoke(cli, ["approvals", "allowlist", "remove", str(entry.id)])
        assert result.exit_code == 0
        assert POLICY.list_entries() == []

    def test_remove_unknown_entry_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["approvals", "allowlist", "remove", "999999"])
        assert result.exit_code != 0
