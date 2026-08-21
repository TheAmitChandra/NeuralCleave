"""Unit tests for neuralcleave.tools.approvals — ApprovalQueue.on_request hook.

Round 4 (2026-08-21 gap analysis) P0: this is the seam AgentRuntime uses to
forward a pending approval into the channel that triggered it. The rest of
ApprovalQueue's request/approve/deny lifecycle predates this file and isn't
re-tested here.
"""

from __future__ import annotations

import pytest

from neuralcleave.tools.approvals import ApprovalQueue


def test_on_request_defaults_to_none() -> None:
    queue = ApprovalQueue()
    assert queue.on_request is None


def test_request_calls_on_request_hook() -> None:
    queue = ApprovalQueue()
    seen = []
    queue.on_request = seen.append

    req = queue.request("shell", "ls", {})

    assert seen == [req]


def test_request_without_hook_does_not_raise() -> None:
    queue = ApprovalQueue()
    queue.request("shell", "ls", {})  # must not raise


def test_a_raising_hook_does_not_block_the_request() -> None:
    """A failed notification must never prevent the command from being
    queued — the web approvals UI stays available as a fallback either way."""
    queue = ApprovalQueue()

    def _boom(_req):
        raise RuntimeError("channel unreachable")

    queue.on_request = _boom

    req = queue.request("shell", "ls", {})

    assert queue.get(req.id) is req


def test_hook_receives_the_request_passed_to_request(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = ApprovalQueue()
    captured = {}

    def _capture(req):
        captured["command"] = req.command
        captured["session_id"] = req.session_id

    queue.on_request = _capture

    queue.request("shell", "git status", {}, session_id="s1")

    assert captured == {"command": "git status", "session_id": "s1"}
