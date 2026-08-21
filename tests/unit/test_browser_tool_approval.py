"""Tests for BrowserAutomationTool require_approval mode.

Mirrors test_shell_tool_approval.py — same APPROVAL_QUEUE gate, applied
here because BrowserAutomationTool's `evaluate` action runs arbitrary
JavaScript and the other actions can submit forms or navigate on the
user's behalf.
"""

from __future__ import annotations

import asyncio

import pytest

from neuralcleave.tools.approvals import APPROVAL_QUEUE
from neuralcleave.tools.browser import BrowserAutomationTool


@pytest.fixture(autouse=True)
def clear_approval_queue():
    """Ensure the global queue is empty before and after each test."""
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)
    yield
    for req_id in list(APPROVAL_QUEUE._entries):
        APPROVAL_QUEUE.deny(req_id)


class TestBrowserToolApproval:
    @pytest.mark.asyncio
    async def test_approval_not_required_does_not_queue_any_request(self) -> None:
        tool = BrowserAutomationTool(require_approval=False)
        before = len(APPROVAL_QUEUE)
        await tool.execute(action="get_url")
        assert len(APPROVAL_QUEUE) == before

    @pytest.mark.asyncio
    async def test_approval_required_queues_request(self) -> None:
        tool = BrowserAutomationTool(require_approval=True, session_id="test-session")

        async def _auto_approve():
            await asyncio.sleep(0.02)
            pending = APPROVAL_QUEUE.pending()
            for item in pending:
                APPROVAL_QUEUE.approve(item["id"])

        task = asyncio.create_task(_auto_approve())
        await tool.execute(action="get_url")
        await task

        assert len(APPROVAL_QUEUE) == 0

    @pytest.mark.asyncio
    async def test_denied_action_returns_error(self) -> None:
        tool = BrowserAutomationTool(require_approval=True, session_id="s")

        async def _auto_deny():
            await asyncio.sleep(0.02)
            for item in APPROVAL_QUEUE.pending():
                APPROVAL_QUEUE.deny(item["id"])

        task = asyncio.create_task(_auto_deny())
        result = await tool.execute(action="navigate", url="https://example.com")
        await task

        assert result.error is not None
        assert "denied" in result.error.lower()

    @pytest.mark.asyncio
    async def test_approval_request_stores_session_id(self) -> None:
        tool = BrowserAutomationTool(require_approval=True, session_id="my-session")

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            assert pending[0]["session_id"] == "my-session"
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(action="get_url")
        await task

    @pytest.mark.asyncio
    async def test_per_call_session_id_overrides_the_constructor_default(self) -> None:
        """BrowserAutomationTool is a single shared instance across every
        channel/session in the live registry — the per-call ``_session_id``
        (forwarded by ToolRegistry.call) must win over the static
        constructor-time value."""
        tool = BrowserAutomationTool(require_approval=True, session_id="constructor-default")

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            assert pending[0]["session_id"] == "per-call-session"
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(action="get_url", _session_id="per-call-session")
        await task

    @pytest.mark.asyncio
    async def test_missing_per_call_session_id_falls_back_to_constructor_default(self) -> None:
        tool = BrowserAutomationTool(require_approval=True, session_id="constructor-default")

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            assert pending[0]["session_id"] == "constructor-default"
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(action="get_url")
        await task

    @pytest.mark.asyncio
    async def test_approval_request_summarizes_action_and_url(self) -> None:
        tool = BrowserAutomationTool(require_approval=True, session_id="s")
        captured: list[str] = []

        async def _check_and_deny():
            await asyncio.sleep(0.01)
            pending = APPROVAL_QUEUE.pending()
            captured.append(pending[0]["command"])
            APPROVAL_QUEUE.deny(pending[0]["id"])

        task = asyncio.create_task(_check_and_deny())
        await tool.execute(action="navigate", url="https://example.com")
        await task

        assert captured[0] == "navigate https://example.com"

    @pytest.mark.asyncio
    async def test_evaluate_action_is_gated_when_approval_required(self) -> None:
        """The highest-risk action (arbitrary JS) must go through the same gate."""
        tool = BrowserAutomationTool(require_approval=True, session_id="s")

        async def _auto_deny():
            await asyncio.sleep(0.01)
            for item in APPROVAL_QUEUE.pending():
                APPROVAL_QUEUE.deny(item["id"])

        task = asyncio.create_task(_auto_deny())
        result = await tool.execute(action="evaluate", expression="document.title")
        await task

        assert result.error is not None
        assert "denied" in result.error.lower()
