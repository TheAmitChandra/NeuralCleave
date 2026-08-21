"""Tests for ShellTool require_approval mode."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from neuralcleave.tools.approval_policy import ApprovalPolicy
from neuralcleave.tools.approvals import APPROVAL_QUEUE
from neuralcleave.tools.shell import ShellTool


@pytest.fixture(autouse=True)
def clear_approval_queue():
    """Ensure the global queue is empty before and after each test."""
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)
    yield
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)


class TestShellToolApproval:
    @pytest.mark.asyncio
    async def test_approval_not_required_does_not_queue_any_request(self) -> None:
        tool = ShellTool(require_approval=False)
        before = len(APPROVAL_QUEUE)
        await tool.execute(command="python --version")
        assert len(APPROVAL_QUEUE) == before

    @pytest.mark.asyncio
    async def test_approval_required_queues_request(self) -> None:
        tool = ShellTool(require_approval=True, session_id="test-session")

        async def _auto_approve():
            await asyncio.sleep(0.02)
            pending = APPROVAL_QUEUE.pending()
            for item in pending:
                APPROVAL_QUEUE.approve(item["id"])

        task = asyncio.create_task(_auto_approve())
        await tool.execute(command="echo hi")
        await task

        assert len(APPROVAL_QUEUE) == 0

    @pytest.mark.asyncio
    async def test_denied_command_returns_error(self) -> None:
        tool = ShellTool(require_approval=True, session_id="s")

        async def _auto_deny():
            await asyncio.sleep(0.02)
            for item in APPROVAL_QUEUE.pending():
                APPROVAL_QUEUE.deny(item["id"])

        task = asyncio.create_task(_auto_deny())
        result = await tool.execute(command="echo hi")
        await task

        assert result.error is not None
        assert "denied" in result.error.lower()

    @pytest.mark.asyncio
    async def test_approval_request_stores_session_id(self) -> None:
        tool = ShellTool(require_approval=True, session_id="my-session")

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            assert pending[0]["session_id"] == "my-session"
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(command="echo check")
        await task

    @pytest.mark.asyncio
    async def test_per_call_session_id_overrides_the_constructor_default(self) -> None:
        """ShellTool is a single shared instance across every channel/session
        in the live registry — the per-call ``_session_id`` (forwarded by
        ToolRegistry.call from the actual originating session) must win over
        whatever static value the tool happened to be constructed with."""
        tool = ShellTool(require_approval=True, session_id="constructor-default")

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            assert pending[0]["session_id"] == "per-call-session"
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(command="echo check", _session_id="per-call-session")
        await task

    @pytest.mark.asyncio
    async def test_missing_per_call_session_id_falls_back_to_constructor_default(self) -> None:
        tool = ShellTool(require_approval=True, session_id="constructor-default")

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            assert pending[0]["session_id"] == "constructor-default"
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(command="echo check")
        await task

    @pytest.mark.asyncio
    async def test_approval_request_stores_command(self) -> None:
        tool = ShellTool(require_approval=True, session_id="s")
        captured: list[str] = []

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            captured.append(pending[0]["command"])
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(command="git log --oneline")
        await task

        assert captured[0] == "git log --oneline"


class TestShellToolApprovalPolicyIntegration:
    """The approval gate consults ApprovalPolicy before queueing a prompt —
    a matched allowlist entry can skip the prompt entirely, and security
    modes can deny outright without ever touching APPROVAL_QUEUE."""

    @pytest.mark.asyncio
    async def test_allowlisted_command_skips_the_queue_entirely(self) -> None:
        policy = ApprovalPolicy(db_path=None, security="allowlist", ask="on-miss")
        policy.add_entry("echo")
        tool = ShellTool(require_approval=True, session_id="s")

        with patch("neuralcleave.tools.approval_policy.POLICY", policy):
            before = len(APPROVAL_QUEUE)
            result = await tool.execute(command="echo hi")

        assert len(APPROVAL_QUEUE) == before
        assert result.error is None

    @pytest.mark.asyncio
    async def test_deny_security_mode_denies_without_queueing(self) -> None:
        policy = ApprovalPolicy(db_path=None, security="deny")
        tool = ShellTool(require_approval=True, session_id="s")

        with patch("neuralcleave.tools.approval_policy.POLICY", policy):
            before = len(APPROVAL_QUEUE)
            result = await tool.execute(command="echo hi")

        assert len(APPROVAL_QUEUE) == before
        assert result.error is not None
        assert "denied by approval policy" in result.error.lower()

    @pytest.mark.asyncio
    async def test_full_security_mode_runs_without_prompting(self) -> None:
        policy = ApprovalPolicy(db_path=None, security="full")
        tool = ShellTool(require_approval=True, session_id="s")

        with patch("neuralcleave.tools.approval_policy.POLICY", policy):
            result = await tool.execute(command="echo hi")

        assert result.error is None
        assert "hi" in result.output

    @pytest.mark.asyncio
    async def test_ask_always_still_prompts_despite_allowlist_match(self) -> None:
        policy = ApprovalPolicy(db_path=None, security="allowlist", ask="always")
        policy.add_entry("echo")
        tool = ShellTool(require_approval=True, session_id="s")

        async def _auto_approve():
            await asyncio.sleep(0.02)
            for item in APPROVAL_QUEUE.pending():
                APPROVAL_QUEUE.approve(item["id"])

        with patch("neuralcleave.tools.approval_policy.POLICY", policy):
            task = asyncio.create_task(_auto_approve())
            result = await tool.execute(command="echo hi")
            await task

        assert result.error is None


class TestShellToolApprovalMetrics:
    """The approval gate records approval_decisions_total by outcome."""

    def _reset(self):
        from neuralcleave.observability.metrics import REGISTRY

        for decision in ("auto_approved", "prompted", "denied_outright"):
            REGISTRY.get("approval_decisions_total").reset(labels={"decision": decision})

    @pytest.mark.asyncio
    async def test_auto_approved_increments_that_label(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        self._reset()
        policy = ApprovalPolicy(db_path=None, security="allowlist", ask="on-miss")
        policy.add_entry("echo")
        tool = ShellTool(require_approval=True, session_id="s")

        with patch("neuralcleave.tools.approval_policy.POLICY", policy):
            await tool.execute(command="echo hi")

        snap = REGISTRY.get("approval_decisions_total").snapshot()
        assert snap.get("decision=auto_approved", 0) == 1
        assert snap.get("decision=prompted", 0) == 0

    @pytest.mark.asyncio
    async def test_denied_outright_increments_that_label(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        self._reset()
        policy = ApprovalPolicy(db_path=None, security="deny")
        tool = ShellTool(require_approval=True, session_id="s")

        with patch("neuralcleave.tools.approval_policy.POLICY", policy):
            await tool.execute(command="echo hi")

        snap = REGISTRY.get("approval_decisions_total").snapshot()
        assert snap.get("decision=denied_outright", 0) == 1

    @pytest.mark.asyncio
    async def test_prompted_increments_that_label(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        self._reset()
        policy = ApprovalPolicy(db_path=None, security="allowlist", ask="on-miss")
        tool = ShellTool(require_approval=True, session_id="s")

        async def _auto_deny():
            await asyncio.sleep(0.02)
            for item in APPROVAL_QUEUE.pending():
                APPROVAL_QUEUE.deny(item["id"])

        with patch("neuralcleave.tools.approval_policy.POLICY", policy):
            task = asyncio.create_task(_auto_deny())
            await tool.execute(command="echo hi")
            await task

        snap = REGISTRY.get("approval_decisions_total").snapshot()
        assert snap.get("decision=prompted", 0) == 1
