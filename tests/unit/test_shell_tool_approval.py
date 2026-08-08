"""Tests for ShellTool require_approval mode."""

from __future__ import annotations

import asyncio

import pytest

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
