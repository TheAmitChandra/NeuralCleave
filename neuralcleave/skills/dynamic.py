"""DynamicPlugin and DynamicFunctionTool — runtime wrappers for user functions.

When a user writes a skill that contains only plain functions (no explicit
Plugin subclass), :class:`SkillWriter` wraps each function in a
:class:`DynamicFunctionTool` and groups them under a :class:`DynamicPlugin`.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from neuralcleave.plugins.base import Plugin, PluginMetadata
from neuralcleave.tools.base import Tool, ToolResult


class DynamicFunctionTool(Tool):
    """Wraps a Python callable (sync or async) as a :class:`Tool`.

    Parameter types are inferred from the function's type annotations.
    Sync functions are run in a thread via :func:`asyncio.to_thread` so the
    event loop is never blocked.

    Args:
        fn:               The callable to wrap.
        tool_name:        Override the tool name (defaults to ``fn.__name__``).
        tool_description: Override the description (defaults to first line of
                          ``fn.__doc__``).
    """

    permissions: list[str] = []

    def __init__(
        self,
        fn: Callable,
        *,
        tool_name: str | None = None,
        tool_description: str | None = None,
    ) -> None:
        self.name = tool_name or fn.__name__
        doc = (fn.__doc__ or "").strip()
        self.description = tool_description or (doc.split("\n")[0] if doc else f"Tool: {self.name}")
        self._fn = fn
        self.parameters = _infer_parameters(fn)

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            if asyncio.iscoroutinefunction(self._fn):
                output = await self._fn(**kwargs)
            else:
                output = await asyncio.to_thread(self._fn, **kwargs)
            return ToolResult(tool=self.name, output=output)
        except Exception as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))


class DynamicPlugin(Plugin):
    """A :class:`Plugin` that wraps a list of :class:`Tool` instances.

    Created automatically by :class:`~neuralcleave.skills.writer.SkillWriter`
    when the user's skill module contains plain functions instead of an
    explicit Plugin subclass.
    """

    def __init__(self, name: str, description: str, tools: list[Tool]) -> None:
        self.metadata = PluginMetadata(
            name=name,
            version="1.0.0",
            plugin_type="tool",
            description=description,
        )
        self._tools = tools

    def get_tools(self) -> list[Tool]:
        return list(self._tools)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_parameters(fn: Callable) -> dict[str, dict[str, Any]]:
    """Return a Tool parameters dict inferred from *fn*'s type hints."""
    params: dict[str, dict[str, Any]] = {}
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return params

    hints: dict[str, Any] = {}
    try:
        hints = fn.__annotations__
    except Exception:
        pass

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        annotation = hints.get(param_name, str)
        params[param_name] = {
            "type": _annotation_to_type_str(annotation),
            "description": param_name,
            "required": param.default is inspect.Parameter.empty,
        }
    return params


def _annotation_to_type_str(annotation: Any) -> str:
    # String annotations arise from `from __future__ import annotations`
    if isinstance(annotation, str):
        _str_map: dict[str, str] = {
            "int": "int",
            "float": "float",
            "bool": "bool",
            "list": "list",
            "dict": "dict",
            "str": "str",
        }
        return _str_map.get(annotation, "str")
    mapping: dict[Any, str] = {
        int: "int",
        float: "float",
        bool: "bool",
        list: "list",
        dict: "dict",
    }
    return mapping.get(annotation, "str")
