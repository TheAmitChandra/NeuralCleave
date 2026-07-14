"""Unit tests for cortexflow_ai.canvas.tool — CanvasTool."""

from __future__ import annotations

import pytest

from cortexflow_ai.canvas.renderer import CanvasRenderer
from cortexflow_ai.canvas.tool import (
    CanvasTool,
    get_canvas_renderer,
    set_canvas_renderer,
)


@pytest.fixture()
def renderer():
    return CanvasRenderer()


@pytest.fixture()
def tool(renderer):
    return CanvasTool(renderer=renderer)


@pytest.fixture()
def tool_no_renderer():
    return CanvasTool(renderer=None)


# ---------------------------------------------------------------------------
# No renderer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_renderer_returns_error(tool_no_renderer):
    result = await tool_no_renderer.execute(action="status")
    assert result.error is not None
    assert not result.success


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_returns_count(tool, renderer):
    result = await tool.execute(action="status")
    assert result.success
    assert result.output["available"] is True
    assert result.output["block_count"] == 0


@pytest.mark.asyncio
async def test_status_reflects_added_blocks(tool, renderer):
    from cortexflow_ai.canvas.block import CanvasBlock
    await renderer.add_block(CanvasBlock.new("text", "hi"))
    result = await tool.execute(action="status")
    assert result.output["block_count"] == 1


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_action(tool, renderer):
    from cortexflow_ai.canvas.block import CanvasBlock
    await renderer.add_block(CanvasBlock.new("text", "to clear"))
    result = await tool.execute(action="clear")
    assert result.success
    assert result.output["cleared"] is True
    assert renderer.block_count() == 0


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_text(tool, renderer):
    result = await tool.execute(action="render_text", content="Hello world", title="T")
    assert result.success
    assert result.output["block_type"] == "text"
    assert renderer.block_count() == 1


@pytest.mark.asyncio
async def test_render_text_no_title(tool, renderer):
    result = await tool.execute(action="render_text", content="plain")
    assert result.success
    assert result.output["title"] == ""


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_markdown(tool, renderer):
    result = await tool.execute(action="render_markdown", content="# Hello")
    assert result.success
    assert result.output["block_type"] == "markdown"


# ---------------------------------------------------------------------------
# render_image
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_image(tool, renderer):
    result = await tool.execute(action="render_image", content="https://example.com/img.png")
    assert result.success
    assert result.output["block_type"] == "image"


# ---------------------------------------------------------------------------
# render_table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_table(tool, renderer):
    result = await tool.execute(
        action="render_table",
        headers=["Name", "Score"],
        rows=[["Alice", 95], ["Bob", 87]],
    )
    assert result.success
    assert result.output["block_type"] == "table"
    state = renderer.get_state()
    block_content = state["blocks"][0]["content"]
    assert block_content["headers"] == ["Name", "Score"]
    assert len(block_content["rows"]) == 2


@pytest.mark.asyncio
async def test_render_table_empty(tool, renderer):
    result = await tool.execute(action="render_table", headers=[], rows=[])
    assert result.success


# ---------------------------------------------------------------------------
# render_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_code(tool, renderer):
    result = await tool.execute(
        action="render_code", content="print('hello')", language="python"
    )
    assert result.success
    assert result.output["block_type"] == "code"
    state = renderer.get_state()
    block_content = state["blocks"][0]["content"]
    assert block_content["code"] == "print('hello')"
    assert block_content["language"] == "python"


@pytest.mark.asyncio
async def test_render_code_no_language(tool, renderer):
    result = await tool.execute(action="render_code", content="x = 1")
    assert result.success
    state = renderer.get_state()
    assert state["blocks"][0]["content"]["language"] == ""


# ---------------------------------------------------------------------------
# render_chart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_chart_bar(tool, renderer):
    result = await tool.execute(
        action="render_chart",
        chart_type="bar",
        labels=["Q1", "Q2", "Q3"],
        values=[100, 200, 150],
    )
    assert result.success
    assert result.output["block_type"] == "chart"
    state = renderer.get_state()
    content = state["blocks"][0]["content"]
    assert content["chart_type"] == "bar"
    assert content["labels"] == ["Q1", "Q2", "Q3"]
    assert content["values"] == [100, 200, 150]


@pytest.mark.asyncio
async def test_render_chart_pie(tool, renderer):
    result = await tool.execute(
        action="render_chart", chart_type="pie",
        labels=["A", "B"], values=[60, 40],
    )
    assert result.success


@pytest.mark.asyncio
async def test_render_chart_line(tool, renderer):
    result = await tool.execute(
        action="render_chart", chart_type="line",
        labels=["Jan", "Feb"], values=[10, 20],
    )
    assert result.success


@pytest.mark.asyncio
async def test_render_chart_default_type(tool, renderer):
    result = await tool.execute(
        action="render_chart", labels=["X"], values=[1],
    )
    assert result.success
    content = renderer.get_state()["blocks"][0]["content"]
    assert content["chart_type"] == "bar"


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_render_html(tool, renderer):
    result = await tool.execute(action="render_html", content="<h1>Hi</h1>")
    assert result.success
    assert result.output["block_type"] == "html"


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_action_returns_error(tool):
    result = await tool.execute(action="do_magic")
    assert not result.success
    assert result.error is not None


# ---------------------------------------------------------------------------
# block_id in output
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_contains_block_id(tool):
    result = await tool.execute(action="render_text", content="id test")
    assert "block_id" in result.output
    assert len(result.output["block_id"]) == 32  # UUID4 hex


# ---------------------------------------------------------------------------
# Module-level renderer injection
# ---------------------------------------------------------------------------


def test_set_get_canvas_renderer():
    r = CanvasRenderer()
    set_canvas_renderer(r)
    assert get_canvas_renderer() is r
    set_canvas_renderer(None)
    assert get_canvas_renderer() is None


@pytest.mark.asyncio
async def test_tool_falls_back_to_module_renderer():
    r = CanvasRenderer()
    set_canvas_renderer(r)
    t = CanvasTool(renderer=None)
    result = await t.execute(action="status")
    assert result.success
    set_canvas_renderer(None)
