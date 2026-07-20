"""Tests for neuralcleave/skills/ — SkillWriter, DynamicPlugin, DynamicFunctionTool,
WriteSkillTool, ListSkillsTool, DeleteSkillTool, and the cortex skills CLI group.

Coverage targets
----------------
- SkillWriter.validate_code — syntax errors, blocked imports, valid code
- SkillWriter.write_skill — happy path, invalid name, bad code, re-write
- SkillWriter.list_skills — empty dir, one skill, multiple skills
- SkillWriter.get_skill_code — found, not found
- SkillWriter.delete_skill — found, not found, unregisters plugin
- SkillWriter._find_plugin_class — module with Plugin, without Plugin
- SkillWriter._wrap_functions_as_plugin — sync/async functions, no functions
- DynamicFunctionTool — sync fn, async fn, error handling, parameter inference
- DynamicPlugin — metadata, get_tools
- _annotation_to_type_str — all supported types, fallback
- _infer_parameters — no hints, partial hints, self/cls skipped
- WriteSkillTool.execute — happy path, missing name, missing code, write error
- ListSkillsTool.execute — empty, with skills
- DeleteSkillTool.execute — happy path, missing name, not found
- CLI cortex skills write/list/show/delete/validate
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from neuralcleave.skills.dynamic import (
    DynamicFunctionTool,
    DynamicPlugin,
    _annotation_to_type_str,
    _infer_parameters,
)
from neuralcleave.skills.writer import (
    SkillInfo,
    SkillWriter,
    _validate_skill_name,
)
from neuralcleave.tools.write_skill_tool import (
    DeleteSkillTool,
    ListSkillsTool,
    WriteSkillTool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_CODE = """\
def greet(name: str) -> str:
    \"\"\"Say hello.\"\"\"
    return f"Hello, {name}!"
"""

ASYNC_CODE = """\
async def fetch(url: str) -> str:
    \"\"\"Fetch a URL.\"\"\"
    return url
"""

PLUGIN_CODE = """\
from neuralcleave.plugins.base import Plugin, PluginMetadata
from neuralcleave.tools.base import Tool, ToolResult

class EchoTool(Tool):
    name = "echo"
    description = "Echo back the input."
    parameters = {"text": {"type": "str", "description": "text to echo"}}
    permissions = []

    async def execute(self, **kwargs):
        return ToolResult(tool=self.name, output=kwargs.get("text", ""))

class EchoPlugin(Plugin):
    metadata = PluginMetadata(
        name="echo_plugin",
        version="1.0.0",
        plugin_type="tool",
        description="Echo plugin for tests",
    )

    def get_tools(self):
        return [EchoTool()]
"""

INVALID_SYNTAX_CODE = "def broken(: str:"

BLOCKED_SUBPROCESS = "import subprocess\nsubprocess.run(['ls'])"
BLOCKED_SUBPROCESS_FROM = "from subprocess import run\nrun(['ls'])"
BLOCKED_CTYPES = "import ctypes"
BLOCKED_WINREG = "from winreg import OpenKey"
BLOCKED_MSVCRT = "import msvcrt"


def _make_writer(tmp_path: Path) -> SkillWriter:
    return SkillWriter(skills_dir=tmp_path / "skills")


# ---------------------------------------------------------------------------
# _validate_skill_name
# ---------------------------------------------------------------------------


def test_validate_name_ok() -> None:
    assert _validate_skill_name("hello") == "hello"


def test_validate_name_hyphen_becomes_underscore() -> None:
    assert _validate_skill_name("my-skill") == "my_skill"


def test_validate_name_uppercase_lowered() -> None:
    assert _validate_skill_name("MySkill") == "myskill"


def test_validate_name_empty_raises() -> None:
    with pytest.raises(ValueError, match="not be empty"):
        _validate_skill_name("")


def test_validate_name_starts_with_digit_raises() -> None:
    with pytest.raises(ValueError, match="must not start with a digit"):
        _validate_skill_name("1bad")


def test_validate_name_invalid_char_raises() -> None:
    with pytest.raises(ValueError, match="invalid characters"):
        _validate_skill_name("bad name!")


def test_validate_name_trailing_underscore_ok() -> None:
    assert _validate_skill_name("skill_") == "skill_"


# ---------------------------------------------------------------------------
# SkillWriter.validate_code
# ---------------------------------------------------------------------------


def test_validate_valid_code(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    assert w.validate_code(SIMPLE_CODE) == []


def test_validate_syntax_error(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    errors = w.validate_code(INVALID_SYNTAX_CODE)
    assert any("SyntaxError" in e for e in errors)


def test_validate_blocked_subprocess(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    errors = w.validate_code(BLOCKED_SUBPROCESS)
    assert any("subprocess" in e for e in errors)


def test_validate_blocked_subprocess_from(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    errors = w.validate_code(BLOCKED_SUBPROCESS_FROM)
    assert any("subprocess" in e for e in errors)


def test_validate_blocked_ctypes(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    errors = w.validate_code(BLOCKED_CTYPES)
    assert any("ctypes" in e for e in errors)


def test_validate_blocked_winreg(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    errors = w.validate_code(BLOCKED_WINREG)
    assert any("winreg" in e for e in errors)


def test_validate_blocked_msvcrt(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    errors = w.validate_code(BLOCKED_MSVCRT)
    assert any("msvcrt" in e for e in errors)


def test_validate_multiple_errors(tmp_path: Path) -> None:
    code = "import subprocess\nimport ctypes"
    w = _make_writer(tmp_path)
    errors = w.validate_code(code)
    assert len(errors) >= 2


def test_validate_nested_blocked_import(tmp_path: Path) -> None:
    code = "import subprocess.run"
    w = _make_writer(tmp_path)
    errors = w.validate_code(code)
    assert any("subprocess" in e for e in errors)


def test_validate_allowed_imports(tmp_path: Path) -> None:
    code = "import os\nimport pathlib\nimport httpx"
    w = _make_writer(tmp_path)
    assert w.validate_code(code) == []


def test_validate_empty_code(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    assert w.validate_code("") == []


def test_validate_async_fn_ok(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    assert w.validate_code(ASYNC_CODE) == []


def test_validate_plugin_class_ok(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    assert w.validate_code(PLUGIN_CODE) == []


# ---------------------------------------------------------------------------
# SkillWriter.write_skill — happy path
# ---------------------------------------------------------------------------


def test_write_skill_creates_file(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    skill_path = tmp_path / "skills" / "greet" / "skill.py"
    assert skill_path.exists()
    assert "def greet" in skill_path.read_text()


def test_write_skill_returns_message(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    msg = w.write_skill("greet", SIMPLE_CODE)
    assert "greet" in msg
    assert "greet" in msg  # tool name in output


def test_write_skill_stores_plugin(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    assert "greet" in w._loaded_skills


def test_write_skill_with_description(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    msg = w.write_skill("greet", SIMPLE_CODE, description="Says hello")
    assert "greet" in msg


def test_write_skill_plugin_class(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("echo_plugin", PLUGIN_CODE)
    plugin = w._loaded_skills["echo_plugin"]
    tools = plugin.get_tools()
    assert any(t.name == "echo" for t in tools)


def test_write_skill_registers_with_registry(tmp_path: Path) -> None:
    mock_registry = MagicMock()
    mock_registry.all_plugins = []
    w = SkillWriter(plugin_registry=mock_registry, skills_dir=tmp_path / "skills")
    w.write_skill("greet", SIMPLE_CODE)
    mock_registry.register.assert_called_once()


def test_write_skill_re_registers_if_existing(tmp_path: Path) -> None:
    mock_plugin = MagicMock()
    mock_plugin.metadata.name = "greet"
    mock_registry = MagicMock()
    mock_registry.all_plugins = [mock_plugin]
    w = SkillWriter(plugin_registry=mock_registry, skills_dir=tmp_path / "skills")
    w.write_skill("greet", SIMPLE_CODE)
    mock_registry.unregister.assert_called_once_with("greet")
    mock_registry.register.assert_called_once()


def test_write_skill_normalises_name(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("My-Skill", SIMPLE_CODE)
    assert "my_skill" in w._loaded_skills


# ---------------------------------------------------------------------------
# SkillWriter.write_skill — error paths
# ---------------------------------------------------------------------------


def test_write_skill_invalid_name_raises(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    with pytest.raises(ValueError):
        w.write_skill("bad name!", SIMPLE_CODE)


def test_write_skill_syntax_error_raises(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    with pytest.raises(ValueError, match="SyntaxError"):
        w.write_skill("bad", INVALID_SYNTAX_CODE)


def test_write_skill_blocked_import_raises(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    with pytest.raises(ValueError, match="subprocess"):
        w.write_skill("bad", BLOCKED_SUBPROCESS)


def test_write_skill_runtime_error_on_bad_module(tmp_path: Path) -> None:
    broken_code = "raise RuntimeError('boom at import')"
    w = _make_writer(tmp_path)
    with pytest.raises(RuntimeError, match="boom at import"):
        w.write_skill("broken", broken_code)


# ---------------------------------------------------------------------------
# SkillWriter.list_skills
# ---------------------------------------------------------------------------


def test_list_skills_empty(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    assert w.list_skills() == []


def test_list_skills_nonexistent_dir(tmp_path: Path) -> None:
    w = SkillWriter(skills_dir=tmp_path / "nonexistent")
    assert w.list_skills() == []


def test_list_skills_one_skill(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    skills = w.list_skills()
    assert len(skills) == 1
    assert skills[0].name == "greet"
    assert skills[0].loaded is True


def test_list_skills_unloaded_skill(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    (skills_dir / "orphan").mkdir(parents=True)
    (skills_dir / "orphan" / "skill.py").write_text("x = 1")
    w = SkillWriter(skills_dir=skills_dir)
    skills = w.list_skills()
    assert any(s.name == "orphan" and not s.loaded for s in skills)


def test_list_skills_sorted(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("zebra", SIMPLE_CODE)
    w.write_skill("apple", SIMPLE_CODE)
    names = [s.name for s in w.list_skills()]
    assert names == sorted(names)


def test_list_skills_description_from_loaded_plugin(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("echo_plugin", PLUGIN_CODE)
    skills = w.list_skills()
    assert any(s.name == "echo_plugin" for s in skills)


def test_list_skills_ignores_non_dirs(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "stray_file.txt").write_text("oops")
    w = SkillWriter(skills_dir=skills_dir)
    assert w.list_skills() == []


# ---------------------------------------------------------------------------
# SkillWriter.get_skill_code
# ---------------------------------------------------------------------------


def test_get_skill_code_found(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    code = w.get_skill_code("greet")
    assert "def greet" in code


def test_get_skill_code_not_found(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    with pytest.raises(FileNotFoundError):
        w.get_skill_code("missing")


# ---------------------------------------------------------------------------
# SkillWriter.delete_skill
# ---------------------------------------------------------------------------


def test_delete_skill_removes_file(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    w.delete_skill("greet")
    assert not (tmp_path / "skills" / "greet" / "skill.py").exists()


def test_delete_skill_removes_from_loaded(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    w.delete_skill("greet")
    assert "greet" not in w._loaded_skills


def test_delete_skill_unregisters_from_registry(tmp_path: Path) -> None:
    mock_registry = MagicMock()
    mock_registry.all_plugins = []
    w = SkillWriter(plugin_registry=mock_registry, skills_dir=tmp_path / "skills")
    w.write_skill("greet", SIMPLE_CODE)
    w.delete_skill("greet")
    mock_registry.unregister.assert_called_once_with("greet")


def test_delete_skill_cleans_sys_modules(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    assert "_NeuralCleave_skill_greet" in sys.modules
    w.delete_skill("greet")
    assert "_NeuralCleave_skill_greet" not in sys.modules


def test_delete_skill_not_found_raises(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    with pytest.raises(FileNotFoundError):
        w.delete_skill("ghost")


def test_delete_skill_no_registry(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    # Should not raise even without registry
    w.delete_skill("greet")


# ---------------------------------------------------------------------------
# SkillWriter._find_plugin_class
# ---------------------------------------------------------------------------


def test_find_plugin_class_found(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("echo_plugin", PLUGIN_CODE)
    plugin = w._loaded_skills["echo_plugin"]
    assert plugin.metadata.name == "echo_plugin"


def test_find_plugin_class_not_found_falls_back_to_dynamic(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    plugin = w._loaded_skills["greet"]
    from neuralcleave.skills.dynamic import DynamicPlugin
    assert isinstance(plugin, DynamicPlugin)


# ---------------------------------------------------------------------------
# SkillWriter._wrap_functions_as_plugin
# ---------------------------------------------------------------------------


def test_wrap_functions_creates_dynamic_plugin(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    from neuralcleave.skills.dynamic import DynamicPlugin
    assert isinstance(w._loaded_skills["greet"], DynamicPlugin)


def test_wrap_functions_creates_tool_per_function(tmp_path: Path) -> None:
    code = """\
def add(a: int, b: int) -> int:
    \"\"\"Add two numbers.\"\"\"
    return a + b

def sub(a: int, b: int) -> int:
    \"\"\"Subtract.\"\"\"
    return a - b
"""
    w = _make_writer(tmp_path)
    w.write_skill("math_skill", code)
    plugin = w._loaded_skills["math_skill"]
    tool_names = {t.name for t in plugin.get_tools()}
    assert "add" in tool_names
    assert "sub" in tool_names


def test_wrap_functions_skips_private(tmp_path: Path) -> None:
    code = """\
def _private() -> None:
    pass

def public() -> str:
    return "hi"
"""
    w = _make_writer(tmp_path)
    w.write_skill("pub_skill", code)
    plugin = w._loaded_skills["pub_skill"]
    tool_names = [t.name for t in plugin.get_tools()]
    assert "_private" not in tool_names
    assert "public" in tool_names


def test_wrap_async_function(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("async_skill", ASYNC_CODE)
    plugin = w._loaded_skills["async_skill"]
    assert any(t.name == "fetch" for t in plugin.get_tools())


def test_wrap_empty_module_gives_no_tools(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("empty_skill", "# nothing here\n")
    plugin = w._loaded_skills["empty_skill"]
    assert plugin.get_tools() == []


# ---------------------------------------------------------------------------
# SkillWriter.load_into_registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_into_registry_no_registry(tmp_path: Path) -> None:
    w = _make_writer(tmp_path)
    w.write_skill("greet", SIMPLE_CODE)
    result = await w.load_into_registry("greet")
    assert result is False


@pytest.mark.asyncio
async def test_load_into_registry_unknown_skill(tmp_path: Path) -> None:
    mock_registry = MagicMock()
    w = SkillWriter(plugin_registry=mock_registry, skills_dir=tmp_path / "skills")
    result = await w.load_into_registry("unknown")
    assert result is False


@pytest.mark.asyncio
async def test_load_into_registry_calls_reload(tmp_path: Path) -> None:
    mock_registry = MagicMock()
    mock_registry.all_plugins = []
    mock_registry.reload_plugin = AsyncMock(return_value=True)
    w = SkillWriter(plugin_registry=mock_registry, skills_dir=tmp_path / "skills")
    w.write_skill("greet", SIMPLE_CODE)
    result = await w.load_into_registry("greet")
    assert result is True
    mock_registry.reload_plugin.assert_called_once_with("greet")


# ---------------------------------------------------------------------------
# DynamicFunctionTool
# ---------------------------------------------------------------------------


def test_dynamic_tool_name_from_fn() -> None:
    def my_fn() -> None:
        pass

    tool = DynamicFunctionTool(my_fn)
    assert tool.name == "my_fn"


def test_dynamic_tool_name_override() -> None:
    def fn() -> None:
        pass

    tool = DynamicFunctionTool(fn, tool_name="custom_name")
    assert tool.name == "custom_name"


def test_dynamic_tool_description_from_docstring() -> None:
    def fn() -> None:
        """Does something."""

    tool = DynamicFunctionTool(fn)
    assert tool.description == "Does something."


def test_dynamic_tool_description_override() -> None:
    def fn() -> None:
        """Original doc."""

    tool = DynamicFunctionTool(fn, tool_description="Override")
    assert tool.description == "Override"


def test_dynamic_tool_description_fallback() -> None:
    def fn() -> None:
        pass

    tool = DynamicFunctionTool(fn)
    assert "fn" in tool.description


@pytest.mark.asyncio
async def test_dynamic_tool_execute_sync() -> None:
    def add(a: int, b: int) -> int:
        return a + b

    tool = DynamicFunctionTool(add)
    result = await tool.execute(a=2, b=3)
    assert result.output == 5
    assert result.error is None


@pytest.mark.asyncio
async def test_dynamic_tool_execute_async() -> None:
    async def fetch(url: str) -> str:
        return f"fetched:{url}"

    tool = DynamicFunctionTool(fetch)
    result = await tool.execute(url="http://example.com")
    assert result.output == "fetched:http://example.com"


@pytest.mark.asyncio
async def test_dynamic_tool_execute_sync_error() -> None:
    def boom() -> None:
        raise ValueError("kaboom")

    tool = DynamicFunctionTool(boom)
    result = await tool.execute()
    assert result.error is not None
    assert "kaboom" in result.error


@pytest.mark.asyncio
async def test_dynamic_tool_execute_async_error() -> None:
    async def fail() -> None:
        raise RuntimeError("async boom")

    tool = DynamicFunctionTool(fail)
    result = await tool.execute()
    assert result.error is not None
    assert "async boom" in result.error


def test_dynamic_tool_parameters_inferred() -> None:
    def fn(name: str, count: int, flag: bool) -> None:
        pass

    tool = DynamicFunctionTool(fn)
    assert tool.parameters["name"]["type"] == "str"
    assert tool.parameters["count"]["type"] == "int"
    assert tool.parameters["flag"]["type"] == "bool"


def test_dynamic_tool_parameter_required_vs_optional() -> None:
    def fn(required: str, optional: str = "default") -> None:
        pass

    tool = DynamicFunctionTool(fn)
    assert tool.parameters["required"]["required"] is True
    assert tool.parameters["optional"]["required"] is False


def test_dynamic_tool_skips_self_cls() -> None:
    class Dummy:
        def method(self, x: str) -> None:
            pass

    tool = DynamicFunctionTool(Dummy().method)
    assert "self" not in tool.parameters


# ---------------------------------------------------------------------------
# _annotation_to_type_str
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "annotation,expected",
    [
        # Actual type objects
        (int, "int"),
        (float, "float"),
        (bool, "bool"),
        (list, "list"),
        (dict, "dict"),
        (str, "str"),
        (None, "str"),
        (bytes, "str"),
        # String annotations (from __future__ import annotations)
        ("int", "int"),
        ("float", "float"),
        ("bool", "bool"),
        ("list", "list"),
        ("dict", "dict"),
        ("str", "str"),
        ("unknown", "str"),
    ],
)
def test_annotation_to_type_str(annotation: object, expected: str) -> None:
    assert _annotation_to_type_str(annotation) == expected


# ---------------------------------------------------------------------------
# _infer_parameters
# ---------------------------------------------------------------------------


def test_infer_parameters_no_hints() -> None:
    def fn(x, y):
        pass

    params = _infer_parameters(fn)
    assert "x" in params
    assert params["x"]["type"] == "str"


def test_infer_parameters_partial_hints() -> None:
    def fn(a: int, b):
        pass

    params = _infer_parameters(fn)
    assert params["a"]["type"] == "int"
    assert params["b"]["type"] == "str"


def test_infer_parameters_empty() -> None:
    def fn() -> None:
        pass

    assert _infer_parameters(fn) == {}


# ---------------------------------------------------------------------------
# DynamicPlugin
# ---------------------------------------------------------------------------


def test_dynamic_plugin_metadata() -> None:
    plugin = DynamicPlugin(name="test", description="A test plugin", tools=[])
    assert plugin.metadata.name == "test"
    assert plugin.metadata.description == "A test plugin"
    assert plugin.metadata.plugin_type == "tool"
    assert plugin.metadata.version == "1.0.0"


def test_dynamic_plugin_get_tools() -> None:
    def fn() -> str:
        return "hi"

    tool = DynamicFunctionTool(fn)
    plugin = DynamicPlugin(name="p", description="desc", tools=[tool])
    assert plugin.get_tools() == [tool]


def test_dynamic_plugin_empty_tools() -> None:
    plugin = DynamicPlugin(name="p", description="desc", tools=[])
    assert plugin.get_tools() == []


# ---------------------------------------------------------------------------
# WriteSkillTool
# ---------------------------------------------------------------------------


def _make_mock_writer(tmp_path: Path) -> SkillWriter:
    return _make_writer(tmp_path)


@pytest.mark.asyncio
async def test_write_skill_tool_happy_path(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = WriteSkillTool(skill_writer=writer)
    result = await tool.execute(name="greet", code=SIMPLE_CODE, description="")
    assert result.error is None
    assert "greet" in result.output


@pytest.mark.asyncio
async def test_write_skill_tool_missing_name(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = WriteSkillTool(skill_writer=writer)
    result = await tool.execute(name="", code=SIMPLE_CODE)
    assert result.error is not None
    assert "name" in result.error


@pytest.mark.asyncio
async def test_write_skill_tool_missing_code(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = WriteSkillTool(skill_writer=writer)
    result = await tool.execute(name="greet", code="")
    assert result.error is not None
    assert "code" in result.error


@pytest.mark.asyncio
async def test_write_skill_tool_validation_error(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = WriteSkillTool(skill_writer=writer)
    result = await tool.execute(name="bad", code=BLOCKED_SUBPROCESS)
    assert result.error is not None
    assert "subprocess" in result.error


@pytest.mark.asyncio
async def test_write_skill_tool_invalid_name(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = WriteSkillTool(skill_writer=writer)
    result = await tool.execute(name="bad name!", code=SIMPLE_CODE)
    assert result.error is not None


def test_write_skill_tool_name() -> None:
    writer = MagicMock()
    tool = WriteSkillTool(skill_writer=writer)
    assert tool.name == "write_skill"


def test_write_skill_tool_has_parameters() -> None:
    writer = MagicMock()
    tool = WriteSkillTool(skill_writer=writer)
    assert "name" in tool.parameters
    assert "code" in tool.parameters


# ---------------------------------------------------------------------------
# ListSkillsTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_skills_tool_empty(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = ListSkillsTool(skill_writer=writer)
    result = await tool.execute()
    assert result.error is None
    assert "No" in result.output


@pytest.mark.asyncio
async def test_list_skills_tool_with_skill(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    writer.write_skill("greet", SIMPLE_CODE)
    tool = ListSkillsTool(skill_writer=writer)
    result = await tool.execute()
    assert "greet" in result.output
    assert "loaded" in result.output


def test_list_skills_tool_name() -> None:
    writer = MagicMock()
    assert ListSkillsTool(skill_writer=writer).name == "list_skills"


# ---------------------------------------------------------------------------
# DeleteSkillTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_skill_tool_happy_path(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    writer.write_skill("greet", SIMPLE_CODE)
    tool = DeleteSkillTool(skill_writer=writer)
    result = await tool.execute(name="greet")
    assert result.error is None
    assert "greet" in result.output


@pytest.mark.asyncio
async def test_delete_skill_tool_missing_name(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = DeleteSkillTool(skill_writer=writer)
    result = await tool.execute(name="")
    assert result.error is not None


@pytest.mark.asyncio
async def test_delete_skill_tool_not_found(tmp_path: Path) -> None:
    writer = _make_mock_writer(tmp_path)
    tool = DeleteSkillTool(skill_writer=writer)
    result = await tool.execute(name="ghost")
    assert result.error is not None


def test_delete_skill_tool_name() -> None:
    writer = MagicMock()
    assert DeleteSkillTool(skill_writer=writer).name == "delete_skill"


# ---------------------------------------------------------------------------
# CLI — cortex skills
# ---------------------------------------------------------------------------


from neuralcleave.cli import cli  # noqa: E402


def _runner(tmp_path: Path) -> CliRunner:
    return CliRunner()


def test_cli_skills_write_from_file(tmp_path: Path) -> None:
    skill_file = tmp_path / "my_skill.py"
    skill_file.write_text(SIMPLE_CODE)
    skills_dir = tmp_path / "skills"

    runner = CliRunner()
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        result = runner.invoke(
            cli,
            ["skills", "write", "greet", "--file", str(skill_file)],
            obj={},
        )
    assert result.exit_code == 0 or "Error" not in result.output


def test_cli_skills_write_inline(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    runner = CliRunner()
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        result = runner.invoke(
            cli,
            ["skills", "write", "greet", "--code", SIMPLE_CODE],
            obj={},
        )
    assert result.exit_code == 0


def test_cli_skills_write_both_flags_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["skills", "write", "greet", "--file", "f.py", "--code", "x=1"],
        obj={},
    )
    assert result.exit_code != 0


def test_cli_skills_write_no_flags_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["skills", "write", "greet"], obj={})
    assert result.exit_code != 0


def test_cli_skills_list_empty(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    runner = CliRunner()
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        result = runner.invoke(cli, ["skills", "list"], obj={})
    assert result.exit_code == 0
    assert "No" in result.output


def test_cli_skills_list_with_skill(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    runner = CliRunner()
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        runner.invoke(cli, ["skills", "write", "greet", "--code", SIMPLE_CODE], obj={})
        result = runner.invoke(cli, ["skills", "list"], obj={})
    assert result.exit_code == 0


def test_cli_skills_show_not_found(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    runner = CliRunner()
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        result = runner.invoke(cli, ["skills", "show", "ghost"], obj={})
    assert result.exit_code != 0


def test_cli_skills_delete_with_yes(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    runner = CliRunner()
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        runner.invoke(cli, ["skills", "write", "greet", "--code", SIMPLE_CODE], obj={})
        result = runner.invoke(cli, ["skills", "delete", "greet", "--yes"], obj={})
    assert result.exit_code == 0


def test_cli_skills_delete_not_found(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    runner = CliRunner()
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        result = runner.invoke(cli, ["skills", "delete", "ghost", "--yes"], obj={})
    assert result.exit_code != 0


def test_cli_skills_validate_valid_file(tmp_path: Path) -> None:
    skill_file = tmp_path / "good.py"
    skill_file.write_text(SIMPLE_CODE)
    runner = CliRunner()
    result = runner.invoke(cli, ["skills", "validate", str(skill_file)], obj={})
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_cli_skills_validate_blocked_import(tmp_path: Path) -> None:
    skill_file = tmp_path / "bad.py"
    skill_file.write_text(BLOCKED_SUBPROCESS)
    runner = CliRunner()
    result = runner.invoke(cli, ["skills", "validate", str(skill_file)], obj={})
    assert result.exit_code != 0


def test_cli_skills_validate_syntax_error(tmp_path: Path) -> None:
    skill_file = tmp_path / "syntax.py"
    skill_file.write_text(INVALID_SYNTAX_CODE)
    runner = CliRunner()
    result = runner.invoke(cli, ["skills", "validate", str(skill_file)], obj={})
    assert result.exit_code != 0


def test_cli_skills_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["skills", "--help"], obj={})
    assert result.exit_code == 0
    assert "write" in result.output
    assert "list" in result.output
    assert "delete" in result.output


# ---------------------------------------------------------------------------
# SkillInfo dataclass
# ---------------------------------------------------------------------------


def test_skill_info_fields() -> None:
    info = SkillInfo(name="x", path=Path("/tmp/x"), loaded=True, description="desc")
    assert info.name == "x"
    assert info.loaded is True
    assert info.description == "desc"


def test_skill_info_default_description() -> None:
    info = SkillInfo(name="x", path=Path("/tmp/x"), loaded=False)
    assert info.description == ""
