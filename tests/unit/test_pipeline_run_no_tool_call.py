"""Tests for CognitivePipeline.run() passthrough when no TOOL_CALL in response."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.registry import ToolRegistry


def _make_pipeline(tool_registry=None) -> CognitivePipeline:
    router = MagicMock()
    gen_result = MagicMock()
    gen_result.text = "Hello, I can help you with that."
    gen_result.model = "test-model"
    gen_result.provider = "test"
    gen_result.usage = {}
    router.generate = AsyncMock(return_value=gen_result)

    memory = MagicMock()
    ctx = MagicMock()
    ctx.to_prompt_blocks.return_value = []
    ctx.token_estimate = 0
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()

    workspace = MagicMock()
    workspace.to_system_prompt.return_value = "You are helpful."

    return CognitivePipeline(
        router=router,
        memory=memory,
        workspace=workspace,
        tool_registry=tool_registry,
    )


def _make_message(text: str = "hello") -> MagicMock:
    msg = MagicMock()
    msg.text = text
    return msg


def _make_session() -> MagicMock:
    session = MagicMock()
    session.session_id = "test-session"
    session.build_prompt.return_value = ""
    session.turn_count = 1
    return session


class TestPipelineRunNoToolCall:
    @pytest.mark.asyncio
    async def test_returns_pipeline_result(self) -> None:
        p = _make_pipeline()
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(_make_message(), _make_session())
        assert result is not None

    @pytest.mark.asyncio
    async def test_response_text_unchanged(self) -> None:
        p = _make_pipeline()
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(_make_message(), _make_session())
        assert result.response == "Hello, I can help you with that."

    @pytest.mark.asyncio
    async def test_run_tool_not_called_when_no_registry(self) -> None:
        p = _make_pipeline(tool_registry=None)
        with (
            patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")),
            patch.object(p, "_run_tool_if_called", new=AsyncMock()) as mock_tool,
        ):
            await p.run(_make_message(), _make_session())
        mock_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_tool_called_when_registry_present(self) -> None:
        registry = ToolRegistry()
        p = _make_pipeline(tool_registry=registry)
        with (
            patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")),
            patch.object(
                p, "_run_tool_if_called",
                new=AsyncMock(return_value=("Hello, I can help you with that.", False))
            ) as mock_tool,
        ):
            await p.run(_make_message(), _make_session())
        mock_tool.assert_called_once()
