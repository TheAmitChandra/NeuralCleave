"""Tests for neuralcleave.tools.approval_notify — channel-forwarded approval
notification and plain-text approve/deny reply resolution (P5, 2026-08-17
gap analysis).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from neuralcleave.tools.approval_notify import (
    format_approval_message,
    notify_channel,
    try_resolve_approval_reply,
)
from neuralcleave.tools.approvals import ApprovalQueue


class TestFormatApprovalMessage:
    def test_includes_the_command(self):
        q = ApprovalQueue()
        req = q.request("shell", "git push --force", {}, session_id="s")
        msg = format_approval_message(req)
        assert "git push --force" in msg

    def test_includes_short_id_for_both_actions(self):
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        msg = format_approval_message(req)
        short_id = req.id[:8]
        assert f"approve {short_id}" in msg
        assert f"deny {short_id}" in msg


class TestNotifyChannel:
    @pytest.mark.asyncio
    async def test_calls_adapter_send_with_target_and_message(self):
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        adapter = AsyncMock()

        ok = await notify_channel(adapter, "user-123", req)

        assert ok is True
        adapter.send.assert_awaited_once()
        call_args = adapter.send.call_args
        assert call_args.args[0] == "user-123"
        assert "ls" in call_args.args[1]

    @pytest.mark.asyncio
    async def test_returns_false_and_does_not_raise_when_send_fails(self):
        q = ApprovalQueue()
        req = q.request("shell", "ls", {}, session_id="s")
        adapter = AsyncMock()
        adapter.send.side_effect = Exception("channel down")

        ok = await notify_channel(adapter, "user-123", req)

        assert ok is False


class TestTryResolveApprovalReply:
    def test_returns_none_for_unrelated_text(self):
        assert try_resolve_approval_reply("hello there") is None

    def test_returns_none_for_action_word_without_id(self):
        assert try_resolve_approval_reply("approve") is None

    def test_returns_none_when_no_pending_request_matches(self):
        assert try_resolve_approval_reply("approve deadbeef") is None

    def test_approve_resolves_matching_pending_request(self):
        from neuralcleave.tools.approvals import APPROVAL_QUEUE

        req = APPROVAL_QUEUE.request("shell", "git status", {}, session_id="s")
        try:
            reply = try_resolve_approval_reply(f"approve {req.id[:8]}")
            assert reply == "Approved: git status"
            assert APPROVAL_QUEUE.get(req.id) is None
        finally:
            APPROVAL_QUEUE.deny(req.id)  # clean up if the assertion above failed

    def test_deny_resolves_matching_pending_request(self):
        from neuralcleave.tools.approvals import APPROVAL_QUEUE

        req = APPROVAL_QUEUE.request("shell", "rm -rf /", {}, session_id="s")
        try:
            reply = try_resolve_approval_reply(f"deny {req.id[:8]}")
            assert reply == "Denied: rm -rf /"
            assert APPROVAL_QUEUE.get(req.id) is None
        finally:
            APPROVAL_QUEUE.deny(req.id)

    def test_is_case_insensitive(self):
        from neuralcleave.tools.approvals import APPROVAL_QUEUE

        req = APPROVAL_QUEUE.request("shell", "ls", {}, session_id="s")
        try:
            reply = try_resolve_approval_reply(f"APPROVE {req.id[:8].upper()}")
            assert reply is not None
            assert reply.startswith("Approved:")
        finally:
            APPROVAL_QUEUE.deny(req.id)

    def test_unrecognized_action_word_returns_none(self):
        from neuralcleave.tools.approvals import APPROVAL_QUEUE

        req = APPROVAL_QUEUE.request("shell", "ls", {}, session_id="s")
        try:
            assert try_resolve_approval_reply(f"maybe {req.id[:8]}") is None
        finally:
            APPROVAL_QUEUE.deny(req.id)
