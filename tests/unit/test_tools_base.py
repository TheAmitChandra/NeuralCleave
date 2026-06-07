"""Unit tests for cortexflow.tools.base — ToolResult and Tool ABC."""

from __future__ import annotations

import pytest

from cortexflow.tools.base import Tool, ToolResult, _py_to_json_type


# ---------------------------------------------------------------------------
# Concrete stub tool for testing the abstract base
# ---------------------------------------------------------------------------


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes back the input string."
    parameters = {
        "text": {
            "type": "str",
            "description": "The text to echo.",
            "required": True,
        },
        "times": {
            "type": "int",
            "description": "How many times to repeat.",
            "required": False,
        },
    }
    permissions = ["none"]

    async def execute(self, text: str = "", times: int = 1, **_) -> ToolResult:
        return ToolResult(tool=self.name, output=text * times)


class _NopermTool(Tool):
    name = "noperm"
    description = "No permissions needed."
    permissions = []

    async def execute(self, **_) -> ToolResult:
        return ToolResult(tool=self.name, output="ok")


# ---------------------------------------------------------------------------
# ToolResult tests
# ---------------------------------------------------------------------------


def test_tool_result_success_when_no_error():
    r = ToolResult(tool="t", output="x")
    assert r.success is True


def test_tool_result_error_not_success():
    r = ToolResult(tool="t", output=None, error="boom")
    assert r.success is False


def test_tool_result_metadata_default_empty():
    r = ToolResult(tool="t", output="x")
    assert r.metadata == {}


def test_tool_result_to_prompt_block_success():
    r = ToolResult(tool="search", output="Python is great")
    block = r.to_prompt_block()
    assert "[TOOL:search]" in block
    assert "Python is great" in block


def test_tool_result_to_prompt_block_error():
    r = ToolResult(tool="search", output=None, error="timeout")
    block = r.to_prompt_block()
    assert "ERROR" in block
    assert "timeout" in block


def test_tool_result_to_prompt_block_non_string_output():
    r = ToolResult(tool="t", output={"key": "value"})
    block = r.to_prompt_block()
    assert "key" in block


# ---------------------------------------------------------------------------
# Tool subclass and get_schema tests
# ---------------------------------------------------------------------------


def test_abstract_tool_requires_execute():
    with pytest.raises(TypeError):
        Tool()  # type: ignore[abstract]


def test_tool_repr():
    t = _EchoTool()
    assert "echo" in repr(t)


def test_tool_get_schema_name_and_description():
    schema = _EchoTool().get_schema()
    assert schema["name"] == "echo"
    assert "Echoes" in schema["description"]


def test_tool_get_schema_required_params():
    schema = _EchoTool().get_schema()
    required = schema["parameters"]["required"]
    assert "text" in required
    assert "times" not in required


def test_tool_get_schema_properties_present():
    schema = _EchoTool().get_schema()
    props = schema["parameters"]["properties"]
    assert "text" in props
    assert "times" in props


def test_tool_get_schema_type_mapping():
    schema = _EchoTool().get_schema()
    props = schema["parameters"]["properties"]
    assert props["text"]["type"] == "string"
    assert props["times"]["type"] == "integer"


def test_tool_empty_params_schema():
    schema = _NopermTool().get_schema()
    assert schema["parameters"]["properties"] == {}
    assert schema["parameters"]["required"] == []


# ---------------------------------------------------------------------------
# _py_to_json_type helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "py_type, expected",
    [
        ("str", "string"),
        ("int", "integer"),
        ("float", "number"),
        ("bool", "boolean"),
        ("list", "array"),
        ("dict", "object"),
        ("unknown_type", "string"),
    ],
)
def test_py_to_json_type(py_type: str, expected: str):
    assert _py_to_json_type(py_type) == expected


# ---------------------------------------------------------------------------
# Async execute tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_echo_tool_execute_returns_result():
    t = _EchoTool()
    result = await t.execute(text="hello", times=2)
    assert result.success
    assert result.output == "hellohello"


@pytest.mark.asyncio
async def test_echo_tool_execute_tool_name_on_result():
    t = _EchoTool()
    result = await t.execute(text="x")
    assert result.tool == "echo"
