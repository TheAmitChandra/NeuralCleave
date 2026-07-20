"""CanvasTool — LLM-callable tool for rendering content to the live canvas."""

from __future__ import annotations

from typing import Any

from neuralcleave.canvas.block import CanvasBlock
from neuralcleave.tools.base import Tool, ToolResult

_canvas_renderer: Any = None


def set_canvas_renderer(renderer: Any) -> None:
    global _canvas_renderer
    _canvas_renderer = renderer


def get_canvas_renderer() -> Any:
    return _canvas_renderer


class CanvasTool(Tool):
    """Render rich content blocks to the live canvas for the user to see.

    Supported actions
    -----------------
    render_text      — plain text paragraph
    render_markdown  — markdown string
    render_image     — image URL (https://) or base64 data URI
    render_table     — table with headers + rows
    render_code      — syntax-highlighted code block
    render_chart     — bar / line / pie chart
    render_html      — raw HTML snippet (sandboxed iframe)
    clear            — remove all blocks from the canvas
    status           — return block count and availability
    """

    name = "canvas"
    description = (
        "Render rich content to the live canvas that the user can see in their browser. "
        "Use render_text or render_markdown for prose, render_table for structured data, "
        "render_code for source code, render_chart for visualisations, "
        "render_image for pictures, and clear to reset the canvas."
    )
    parameters: dict[str, dict[str, Any]] = {
        "action": {
            "type": "string",
            "enum": [
                "render_text",
                "render_markdown",
                "render_image",
                "render_table",
                "render_code",
                "render_chart",
                "render_html",
                "clear",
                "status",
            ],
            "description": "The canvas operation to perform.",
        },
        "content": {
            "type": "string",
            "description": (
                "Text/markdown/image-URL/HTML content for render_* actions "
                "(not used for table, chart, clear, or status)."
            ),
        },
        "title": {
            "type": "string",
            "description": "Optional block title displayed above the content.",
        },
        "language": {
            "type": "string",
            "description": "Programming language hint for render_code (e.g. 'python', 'json').",
        },
        "headers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Column header labels for render_table.",
        },
        "rows": {
            "type": "array",
            "items": {"type": "array"},
            "description": "Row data (list of lists) for render_table.",
        },
        "chart_type": {
            "type": "string",
            "enum": ["bar", "line", "pie"],
            "description": "Chart style for render_chart.",
        },
        "labels": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Category labels for render_chart.",
        },
        "values": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Numeric data values for render_chart.",
        },
    }

    def __init__(self, renderer: Any = None) -> None:
        self._renderer = renderer

    async def execute(self, **kwargs: Any) -> ToolResult:
        action: str = kwargs.get("action", "")
        renderer = self._renderer or get_canvas_renderer()

        if renderer is None:
            return ToolResult(
                tool=self.name,
                output=None,
                error="Canvas renderer not initialised — gateway must be started first",
            )

        if action == "status":
            return ToolResult(
                tool=self.name,
                output={
                    "available": True,
                    "block_count": renderer.block_count(),
                    "subscriber_count": renderer.subscriber_count(),
                },
                error=None,
                metadata={},
            )

        if action == "clear":
            await renderer.clear()
            return ToolResult(
                tool=self.name,
                output={"cleared": True},
                error=None,
                metadata={},
            )

        # Resolve block_type from action (strip "render_" prefix)
        if not action.startswith("render_"):
            return ToolResult(
                tool=self.name,
                output=None,
                error=f"Unknown action {action!r}",
            )

        block_type = action[len("render_"):]
        title: str = kwargs.get("title", "")

        if block_type == "table":
            content: Any = {
                "headers": kwargs.get("headers", []),
                "rows": kwargs.get("rows", []),
            }
        elif block_type == "chart":
            content = {
                "chart_type": kwargs.get("chart_type", "bar"),
                "labels": kwargs.get("labels", []),
                "values": kwargs.get("values", []),
            }
        elif block_type == "code":
            content = {
                "code": kwargs.get("content", ""),
                "language": kwargs.get("language", ""),
            }
        else:
            content = kwargs.get("content", "")

        try:
            block = CanvasBlock.new(block_type, content, title)
        except ValueError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        await renderer.add_block(block)
        return ToolResult(
            tool=self.name,
            output={"block_id": block.id, "block_type": block_type, "title": title},
            error=None,
            metadata={"block_id": block.id},
        )
