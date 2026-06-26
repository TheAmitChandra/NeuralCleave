"""Unit tests for cortexflow_sdk.tools — Tool / ToolResult."""

from __future__ import annotations

import pytest
from cortexflow_sdk import Tool, ToolResult


def test_tool_result_success_when_no_error():
    r = ToolResult(tool="t", output="ok")
    assert r.success is True


def test_tool_result_failure_when_error_set():
    r = ToolResult(tool="t", output=None, error="boom")
    assert r.success is False


def test_to_prompt_block_success():
    r = ToolResult(tool="echo", output="hello")
    assert r.to_prompt_block() == "[TOOL:echo]\nhello"


def test_to_prompt_block_error():
    r = ToolResult(tool="echo", output=None, error="failed")
    assert r.to_prompt_block() == "[TOOL:echo ERROR] failed"


def test_to_prompt_block_stringifies_non_string_output():
    r = ToolResult(tool="calc", output=42)
    assert r.to_prompt_block() == "[TOOL:calc]\n42"


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes the input."
    parameters = {
        "text": {"type": "str", "description": "Text to echo", "required": True},
        "loud": {"type": "bool", "description": "Shout it", "required": False},
    }
    permissions = ["network"]

    async def execute(self, text: str, loud: bool = False) -> ToolResult:
        return ToolResult(tool=self.name, output=text.upper() if loud else text)


@pytest.mark.asyncio
async def test_subclassed_tool_executes():
    tool = _EchoTool()
    result = await tool.execute(text="hi", loud=True)
    assert result.output == "HI"


def test_get_schema_marks_required_params():
    schema = _EchoTool().get_schema()
    assert schema["name"] == "echo"
    assert "text" in schema["parameters"]["required"]
    assert "loud" not in schema["parameters"]["required"]


def test_get_schema_maps_python_types_to_json_types():
    schema = _EchoTool().get_schema()
    assert schema["parameters"]["properties"]["loud"]["type"] == "boolean"
    assert schema["parameters"]["properties"]["text"]["type"] == "string"


def test_tool_repr_includes_name():
    assert repr(_EchoTool()) == "_EchoTool(name='echo')"


def test_tool_is_abstract():
    with pytest.raises(TypeError):
        Tool()  # type: ignore[abstract]
