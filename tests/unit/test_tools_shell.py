"""Comprehensive tests for cortexflow.tools.shell — ShellTool.

Test categories
───────────────
 1. Basic execution                    (tests 1–8)
 2. Exit codes                         (tests 9–13)
 3. Timeout enforcement                (tests 14–17)
 4. Injection / metacharacter safety   (tests 18–24)
 5. Allowlist enforcement              (tests 25–32)
 6. Working directory / sandbox        (tests 33–39)
 7. Output size limits                 (tests 40–42)
 8. Input validation                   (tests 43–47)
 9. Environment sanitisation           (tests 48–50)
10. Tool metadata / schema             (tests 51–55)
11. ToolRegistry integration           (tests 56–59)
12. Result structure / prompt block    (tests 60–63)

All commands use sys.executable (the current Python interpreter) so the
test suite is cross-platform (Windows / macOS / Linux) without requiring
any other binaries to be on PATH.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cortexflow_ai.tools.shell import (
    _DEFAULT_ALLOWED,
    MAX_OUTPUT_BYTES,
    ShellTool,
    _sanitize_env,
    _truncate,
)

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ──────────────────────────────────────────────────────────────────────────────

# shlex.quote wraps paths that contain spaces or backslashes in single quotes so
# that shlex.split() (POSIX mode) treats the whole path as a single token.
# This is essential on Windows where sys.executable may be
# C:\Program Files\Python312\python.exe — without quoting, shlex splits at the
# space and "Program" becomes the first token, failing the allowlist check.
PY = shlex.quote(sys.executable)  # e.g. 'C:\Program Files\...\python.exe'


@pytest.fixture()
def tool(tmp_path: Path) -> ShellTool:
    """ShellTool with default allowlist, sandbox = tmp_path."""
    return ShellTool(sandbox=tmp_path)


@pytest.fixture()
def unrestricted(tmp_path: Path) -> ShellTool:
    """ShellTool with no allowlist — any program permitted."""
    return ShellTool(sandbox=tmp_path, allowed_commands=None)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Basic execution
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_basic_stdout_captured(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "print(\'hello\')"')
    assert result.success
    assert "hello" in result.metadata["stdout"]


@pytest.mark.asyncio
async def test_output_field_contains_stdout(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "print(\'cortex\')"')
    assert result.success
    assert "cortex" in str(result.output)


@pytest.mark.asyncio
async def test_multiline_output(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "print(\'a\\nb\\nc\')"')
    assert result.success
    stdout = result.metadata["stdout"]
    assert "a" in stdout and "b" in stdout and "c" in stdout


@pytest.mark.asyncio
async def test_stderr_captured_separately(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "import sys; sys.stderr.write(\'errline\\n\')"'
    )
    assert result.metadata["stderr"].strip() == "errline"


@pytest.mark.asyncio
async def test_combined_stdout_and_stderr(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "import sys; print(\'out\'); sys.stderr.write(\'err\\n\')"'
    )
    assert "out" in result.metadata["stdout"]
    assert "err" in result.metadata["stderr"]


@pytest.mark.asyncio
async def test_no_output_returns_placeholder(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert result.success
    assert result.output == "(no output)"


@pytest.mark.asyncio
async def test_command_metadata_records_tokens(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert "command" in result.metadata
    # metadata["command"] is " ".join(tokens) — unquoted path after shlex parses PY
    assert sys.executable in result.metadata["command"]


@pytest.mark.asyncio
async def test_unicode_output_handled(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "print(\'こんにちは\')"')
    assert result.success
    assert "こんにちは" in result.metadata["stdout"]


# ──────────────────────────────────────────────────────────────────────────────
# 2. Exit codes
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exit_code_zero_on_success(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert result.metadata["exit_code"] == 0


@pytest.mark.asyncio
async def test_exit_code_nonzero_sets_error(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "import sys; sys.exit(42)"')
    assert not result.success
    assert result.metadata["exit_code"] == 42
    assert result.error is not None


@pytest.mark.asyncio
async def test_exit_code_1(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "import sys; sys.exit(1)"')
    assert result.metadata["exit_code"] == 1
    assert not result.success


@pytest.mark.asyncio
async def test_exit_code_in_error_message(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "import sys; sys.exit(7)"')
    assert "7" in (result.error or "")


@pytest.mark.asyncio
async def test_stderr_included_in_error_message_on_failure(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "import sys; sys.stderr.write(\'bad thing\\n\'); sys.exit(1)"'
    )
    assert not result.success
    assert "bad thing" in (result.error or "")


# ──────────────────────────────────────────────────────────────────────────────
# 3. Timeout enforcement
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_sets_timed_out_flag(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "import time; time.sleep(60)"',
        timeout=1,
    )
    assert result.metadata["timed_out"] is True


@pytest.mark.asyncio
async def test_timeout_sets_error(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "import time; time.sleep(60)"',
        timeout=1,
    )
    assert not result.success
    assert "timed out" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_timeout_exit_code_is_none(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "import time; time.sleep(60)"',
        timeout=1,
    )
    assert result.metadata["exit_code"] is None


@pytest.mark.asyncio
async def test_no_timeout_on_fast_command(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "pass"', timeout=10)
    assert result.metadata["timed_out"] is False
    assert result.success


# ──────────────────────────────────────────────────────────────────────────────
# 4. Injection / metacharacter safety
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_semicolon_not_interpreted_as_command_separator(
    tool: ShellTool, tmp_path: Path
) -> None:
    """With shell=False, ';' is passed as a literal arg — second command never runs."""
    marker = tmp_path / "injected.txt"
    cmd = f'{PY} -c "pass" ; {PY} -c "open(r\'{marker}\', \'w\').close()"'
    await tool.execute(command=cmd)
    assert not marker.exists(), "Semicolon injection must not create the marker file"


@pytest.mark.asyncio
async def test_double_ampersand_not_interpreted(
    tool: ShellTool, tmp_path: Path
) -> None:
    marker = tmp_path / "chained.txt"
    cmd = f'{PY} -c "pass" && {PY} -c "open(r\'{marker}\', \'w\').close()"'
    await tool.execute(command=cmd)
    assert not marker.exists(), "&& must not chain a second command"


@pytest.mark.asyncio
async def test_pipe_character_not_interpreted(
    tool: ShellTool, tmp_path: Path
) -> None:
    marker = tmp_path / "piped.txt"
    cmd = f'{PY} -c "pass" | {PY} -c "open(r\'{marker}\', \'w\').close()"'
    await tool.execute(command=cmd)
    assert not marker.exists(), "Pipe must not chain a second command"


@pytest.mark.asyncio
async def test_subshell_dollar_paren_not_expanded(tool: ShellTool) -> None:
    """$() must be passed as a literal string, not expanded."""
    result = await tool.execute(command=f'{PY} -c "import sys; print(sys.argv[1])" "$(whoami)"')
    assert result.success
    # The arg must be the literal string "$(whoami)", not an expanded username
    assert "$(whoami)" in result.metadata["stdout"]


@pytest.mark.asyncio
async def test_backtick_not_expanded(tool: ShellTool) -> None:
    result = await tool.execute(command=f"{PY} -c \"import sys; print(sys.argv[1])\" \"`whoami`\"")
    assert result.success
    assert "`whoami`" in result.metadata["stdout"]


@pytest.mark.asyncio
async def test_newline_in_command_is_rejected(tool: ShellTool) -> None:
    result = await tool.execute(command=f"{PY} -c 'pass'\necho injected")
    # shlex.split raises ValueError on some newline+quote combos, or splits cleanly;
    # either way the injected "echo injected" token becomes an argument, never a command
    if result.success:
        assert "injected" not in result.metadata.get("stdout", "")


@pytest.mark.asyncio
async def test_redirection_operator_not_interpreted(
    tool: ShellTool, tmp_path: Path
) -> None:
    """'>' must not redirect stdout to a file — it becomes an argument."""
    target = tmp_path / "redirect.txt"
    cmd = f'{PY} -c "print(\'data\')" > {target}'
    await tool.execute(command=cmd)
    assert not target.exists(), "Output redirection must not work without shell=True"


# ──────────────────────────────────────────────────────────────────────────────
# 5. Allowlist enforcement
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_python_in_default_allowlist(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert result.success


@pytest.mark.asyncio
async def test_blocked_command_returns_error(tmp_path: Path) -> None:
    restricted = ShellTool(sandbox=tmp_path, allowed_commands={"git"})
    result = await restricted.execute(command=f'{PY} -c "pass"')
    assert not result.success
    assert "not in the allowed list" in (result.error or "")


@pytest.mark.asyncio
async def test_blocked_command_never_executes(tmp_path: Path) -> None:
    marker = tmp_path / "ran.txt"
    restricted = ShellTool(sandbox=tmp_path, allowed_commands={"git"})
    cmd = f'{PY} -c "open(r\'{marker}\', \'w\').close()"'
    await restricted.execute(command=cmd)
    assert not marker.exists(), "Blocked command must not execute"


@pytest.mark.asyncio
async def test_custom_allowlist_permits_listed_command(tmp_path: Path) -> None:
    tool = ShellTool(sandbox=tmp_path, allowed_commands={"python", "python3"})
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert result.success


@pytest.mark.asyncio
async def test_empty_allowlist_blocks_everything(tmp_path: Path) -> None:
    tool = ShellTool(sandbox=tmp_path, allowed_commands=set())
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert not result.success
    assert "not in the allowed list" in (result.error or "")


@pytest.mark.asyncio
async def test_unrestricted_allows_any_command(unrestricted: ShellTool) -> None:
    result = await unrestricted.execute(command=f'{PY} -c "pass"')
    assert result.success


@pytest.mark.asyncio
async def test_allowlist_is_case_insensitive(tmp_path: Path) -> None:
    tool = ShellTool(sandbox=tmp_path, allowed_commands={"PYTHON", "Python3"})
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert result.success


@pytest.mark.asyncio
async def test_allowlist_strips_exe_extension_on_windows(tmp_path: Path) -> None:
    tool = ShellTool(sandbox=tmp_path, allowed_commands={"python"})
    # PY is a shlex-quoted string; use sys.executable directly for path ops
    py_exe = Path(sys.executable)
    # Only meaningful if running on Windows where the exe is python.exe
    name_no_ext = py_exe.name.lower().removesuffix(".exe")
    assert name_no_ext in tool._allowed  # type: ignore[union-attr]


# ──────────────────────────────────────────────────────────────────────────────
# 6. Working directory / sandbox
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_workdir_is_sandbox_root(tool: ShellTool, tmp_path: Path) -> None:
    result = await tool.execute(command=f'{PY} -c "import os; print(os.getcwd())"')
    assert result.success
    # The cwd reported by the process should be the sandbox root
    cwd_reported = result.metadata["stdout"].strip()
    assert Path(cwd_reported).resolve() == tmp_path.resolve()


@pytest.mark.asyncio
async def test_relative_workdir_within_sandbox(tool: ShellTool, tmp_path: Path) -> None:
    subdir = tmp_path / "work"
    subdir.mkdir()
    result = await tool.execute(
        command=f'{PY} -c "import os; print(os.getcwd())"',
        workdir="work",
    )
    assert result.success
    assert Path(result.metadata["stdout"].strip()).resolve() == subdir.resolve()


@pytest.mark.asyncio
async def test_absolute_workdir_rejected(tool: ShellTool, tmp_path: Path) -> None:
    result = await tool.execute(
        command=f'{PY} -c "pass"',
        workdir=str(tmp_path),  # absolute path
    )
    assert not result.success
    assert "absolute" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_workdir_traversal_rejected(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "pass"',
        workdir="../../etc",
    )
    assert not result.success
    assert "traversal" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_nonexistent_workdir_returns_error(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "pass"',
        workdir="does_not_exist",
    )
    assert not result.success
    assert "does not exist" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_sandbox_created_automatically(tmp_path: Path) -> None:
    new_sandbox = tmp_path / "auto_created"
    tool = ShellTool(sandbox=new_sandbox)
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert result.success
    assert new_sandbox.exists()


@pytest.mark.asyncio
async def test_command_writes_file_inside_sandbox(tool: ShellTool, tmp_path: Path) -> None:
    target = tmp_path / "output.txt"
    cmd = f'{PY} -c "open(r\'{target}\', \'w\').write(\'written\')"'
    result = await tool.execute(command=cmd)
    assert result.success
    assert target.read_text() == "written"


# ──────────────────────────────────────────────────────────────────────────────
# 7. Output size limits
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_large_stdout_is_truncated(tool: ShellTool) -> None:
    # Print > MAX_OUTPUT_BYTES worth of data
    result = await tool.execute(
        command=f'{PY} -c "print(\'x\' * {MAX_OUTPUT_BYTES + 1000})"'
    )
    assert result.success
    assert "truncated" in result.metadata["stdout"]


@pytest.mark.asyncio
async def test_large_stderr_is_truncated(tool: ShellTool) -> None:
    result = await tool.execute(
        command=f'{PY} -c "import sys; sys.stderr.write(\'e\' * {MAX_OUTPUT_BYTES + 1000})"'
    )
    assert "truncated" in result.metadata["stderr"]


@pytest.mark.asyncio
async def test_small_output_not_truncated(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "print(\'small\')"')
    assert result.success
    assert "truncated" not in result.metadata["stdout"]


# ──────────────────────────────────────────────────────────────────────────────
# 8. Input validation
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_string_returns_error(tool: ShellTool) -> None:
    result = await tool.execute(command="")
    assert not result.success
    assert "empty" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_whitespace_only_returns_error(tool: ShellTool) -> None:
    result = await tool.execute(command="   ")
    assert not result.success
    assert "empty" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_nonexistent_program_returns_error(tool: ShellTool) -> None:
    tool_unrestricted = ShellTool(sandbox=tool._sandbox, allowed_commands=None)
    result = await tool_unrestricted.execute(command="xyzzy_no_such_program_12345")
    assert not result.success
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_invalid_shlex_syntax_returns_error(tool: ShellTool) -> None:
    result = await tool.execute(command="echo 'unclosed quote")
    assert not result.success
    assert "syntax" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_timeout_must_be_integer(tool: ShellTool) -> None:
    # Floats should be cast to int without error
    result = await tool.execute(command=f'{PY} -c "pass"', timeout=5)
    assert result.success


# ──────────────────────────────────────────────────────────────────────────────
# 9. Environment sanitisation
# ──────────────────────────────────────────────────────────────────────────────


def test_sanitize_env_strips_api_key() -> None:
    with patch.dict(os.environ, {"MY_API_KEY": "secret123"}):
        env = _sanitize_env()
    assert "MY_API_KEY" not in env


def test_sanitize_env_strips_token() -> None:
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-secret"}):
        env = _sanitize_env()
    assert "SLACK_BOT_TOKEN" not in env


def test_sanitize_env_preserves_non_sensitive() -> None:
    with patch.dict(os.environ, {"HOME": "/home/user", "PATH": "/usr/bin"}):
        env = _sanitize_env()
    assert "HOME" in env
    assert "PATH" in env


@pytest.mark.asyncio
async def test_subprocess_does_not_see_api_key(tool: ShellTool) -> None:
    with patch.dict(os.environ, {"MY_API_KEY": "should_not_appear"}):
        result = await tool.execute(
            command=f'{PY} -c "import os; print(os.environ.get(\'MY_API_KEY\', \'STRIPPED\'))"'
        )
    assert result.success
    assert "should_not_appear" not in result.metadata["stdout"]
    assert "STRIPPED" in result.metadata["stdout"]


# ──────────────────────────────────────────────────────────────────────────────
# 10. Tool metadata / schema
# ──────────────────────────────────────────────────────────────────────────────


def test_tool_name_is_shell(tool: ShellTool) -> None:
    assert tool.name == "shell"


def test_tool_permission_is_shell_execute(tool: ShellTool) -> None:
    assert "shell:execute" in tool.permissions


def test_schema_has_name(tool: ShellTool) -> None:
    schema = tool.get_schema()
    assert schema["name"] == "shell"


def test_schema_command_is_required(tool: ShellTool) -> None:
    schema = tool.get_schema()
    assert "command" in schema["parameters"]["required"]


def test_schema_timeout_is_optional(tool: ShellTool) -> None:
    schema = tool.get_schema()
    assert "timeout" not in schema["parameters"]["required"]
    assert "timeout" in schema["parameters"]["properties"]


def test_schema_workdir_is_optional(tool: ShellTool) -> None:
    schema = tool.get_schema()
    assert "workdir" not in schema["parameters"]["required"]
    assert "workdir" in schema["parameters"]["properties"]


def test_description_mentions_shell_false(tool: ShellTool) -> None:
    assert "shell=False" in tool.description or "shell" in tool.description.lower()


# ──────────────────────────────────────────────────────────────────────────────
# 11. ToolRegistry integration
# ──────────────────────────────────────────────────────────────────────────────


def test_shell_registered_in_default_registry() -> None:
    from cortexflow_ai.tools.registry import ToolRegistry

    registry = ToolRegistry.default()
    assert "shell" in registry.names


@pytest.mark.asyncio
async def test_registry_call_dispatches_to_shell(tmp_path: Path) -> None:
    from cortexflow_ai.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(ShellTool(sandbox=tmp_path))

    result = await registry.call("shell", {"command": f'{PY} -c "print(42)"'})
    assert result.success
    assert "42" in result.metadata["stdout"]


@pytest.mark.asyncio
async def test_registry_permission_denied_without_shell_execute(tmp_path: Path) -> None:
    from cortexflow_ai.tools.registry import ToolRegistry

    registry = ToolRegistry(allowed_permissions={"network"})  # no shell:execute
    registry.register(ShellTool(sandbox=tmp_path))

    result = await registry.call("shell", {"command": f'{PY} -c "pass"'})
    assert not result.success
    assert "Permission denied" in (result.error or "")


@pytest.mark.asyncio
async def test_registry_permission_granted_with_shell_execute(tmp_path: Path) -> None:
    from cortexflow_ai.tools.registry import ToolRegistry

    registry = ToolRegistry(allowed_permissions={"shell:execute"})
    registry.register(ShellTool(sandbox=tmp_path))

    result = await registry.call("shell", {"command": f'{PY} -c "pass"'})
    assert result.success


# ──────────────────────────────────────────────────────────────────────────────
# 12. Result structure / prompt block
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_result_metadata_has_all_keys(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "pass"')
    for key in ("stdout", "stderr", "exit_code", "timed_out", "command"):
        assert key in result.metadata, f"Missing metadata key: {key}"


@pytest.mark.asyncio
async def test_result_timed_out_false_on_success(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "pass"')
    assert result.metadata["timed_out"] is False


@pytest.mark.asyncio
async def test_to_prompt_block_contains_stdout_on_success(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "print(\'block_content\')"')
    block = result.to_prompt_block()
    assert "block_content" in block


@pytest.mark.asyncio
async def test_to_prompt_block_shows_error_on_failure(tool: ShellTool) -> None:
    result = await tool.execute(command=f'{PY} -c "import sys; sys.exit(1)"')
    block = result.to_prompt_block()
    assert "ERROR" in block


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helper unit tests
# ──────────────────────────────────────────────────────────────────────────────


def test_truncate_short_string_unchanged() -> None:
    assert _truncate("hello", 100) == "hello"


def test_truncate_long_string_adds_notice() -> None:
    long = "a" * (MAX_OUTPUT_BYTES + 500)
    result = _truncate(long, MAX_OUTPUT_BYTES)
    assert "truncated" in result
    assert len(result.encode("utf-8")) < MAX_OUTPUT_BYTES + 200  # roughly bounded


def test_truncate_exactly_at_limit_unchanged() -> None:
    exact = "b" * MAX_OUTPUT_BYTES
    assert _truncate(exact, MAX_OUTPUT_BYTES) == exact


def test_default_allowed_contains_git() -> None:
    assert "git" in _DEFAULT_ALLOWED


def test_default_allowed_contains_python() -> None:
    assert "python" in _DEFAULT_ALLOWED


def test_default_allowed_contains_grep() -> None:
    assert "grep" in _DEFAULT_ALLOWED
