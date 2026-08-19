"""Tests for ApprovalQueue and ApprovalRequest."""

from __future__ import annotations

import asyncio
import time

import pytest

from neuralcleave.tools.approvals import ApprovalQueue, ApprovalRequest


class TestApprovalQueue:
    def test_initially_empty(self) -> None:
        q = ApprovalQueue()
        assert len(q) == 0

    def test_request_creates_entry(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s1")
        assert isinstance(req, ApprovalRequest)
        assert len(q) == 1

    def test_request_stores_correct_command(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "git status", {}, session_id="s1")
        assert req.command == "git status"

    def test_request_stores_tool_name(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="x")
        assert req.tool_name == "shell"

    def test_request_stores_session_id(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="my-session")
        assert req.session_id == "my-session"

    def test_request_timestamp_is_recent(self) -> None:
        before = time.time()
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        after = time.time()
        assert before <= req.created_at <= after

    def test_pending_returns_all_open_requests(self) -> None:
        q = ApprovalQueue()
        q.request("shell", "cmd1", {}, session_id="s")
        q.request("shell", "cmd2", {}, session_id="s")
        pending = q.pending()
        assert len(pending) == 2

    def test_approve_removes_from_pending(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        q.approve(req.id)
        assert len(q) == 0

    def test_approve_unknown_id_returns_false(self) -> None:
        q = ApprovalQueue()
        assert q.approve("nonexistent-id") is False

    def test_deny_removes_from_pending(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "rm -rf /", {}, session_id="s")
        q.deny(req.id)
        assert len(q) == 0

    def test_deny_unknown_id_returns_false(self) -> None:
        q = ApprovalQueue()
        assert q.deny("ghost") is False

    @pytest.mark.asyncio
    async def test_wait_returns_true_after_approve(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")

        async def _approve():
            await asyncio.sleep(0.01)
            q.approve(req.id)

        asyncio.create_task(_approve())
        result = await req.wait(timeout=5.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_returns_false_after_deny(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")

        async def _deny():
            await asyncio.sleep(0.01)
            q.deny(req.id)

        asyncio.create_task(_deny())
        result = await req.wait(timeout=5.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_returns_false_on_timeout(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        result = await req.wait(timeout=0.05)
        assert result is False


class TestApprovalQueueGet:
    def test_get_returns_matching_request(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "git status", {}, session_id="s")
        found = q.get(req.id)
        assert found is req

    def test_get_unknown_id_returns_none(self) -> None:
        q = ApprovalQueue()
        assert q.get("nonexistent-id") is None

    def test_get_does_not_remove_the_entry(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        q.get(req.id)
        assert len(q) == 1
        assert q.get(req.id) is not None

    def test_get_does_not_resolve_the_waiter(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        q.get(req.id)
        assert req._event.is_set() is False

    def test_get_after_approve_returns_none(self) -> None:
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        q.approve(req.id)
        assert q.get(req.id) is None
