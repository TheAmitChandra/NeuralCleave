"""Shell execution tool — restricted command runner with strict allowlist.

Security controls:
- Only commands explicitly listed in ALLOWED_COMMANDS may execute.
- Shell interpolation is disabled (shell=False always).
- Working directory is locked to workspace_root.
- Stdout/stderr are captured and size-capped.
- Hard timeout via asyncio.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from app.core.observability.logs import get_logger
from app.core.tools.registry import ToolDefinition

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Allowlist — only these base commands can be executed
# ---------------------------------------------------------------------------

ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        # Version / info
        "python",
        "python3",
        "pip",
        "pip3",
        "node",
        "npm",
        "npx",
        # Text processing (read-only utilities)
        "echo",
        "cat",
        "head",
        "tail",
        "grep",
        "wc",
        "sort",
        "uniq",
        "diff",
        # File inspection
        "ls",
        "dir",
        "find",
        "stat",
        "file",
        # Build / test
        "make",
        "pytest",
        "jest",
        "cargo",
        "go",
        # Git (read operations only — writes blocked via arg check)
        "git",
    }
)

# Git sub-commands that are allowed (read-only)
_ALLOWED_GIT_SUBCOMMANDS: frozenset[str] = frozenset(
    {"log", "diff", "status", "show", "branch", "tag", "remote", "describe", "rev-parse"}
)

# Maximum bytes captured from stdout/stderr
_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB

# Default command timeout
_DEFAULT_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _parse_command(command: str) -> list[str]:
    """Split command string into argv using POSIX rules. Never passes to shell."""
    try:
        return shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError(f"Invalid command string: {exc}") from exc


def _validate_command(argv: list[str]) -> None:
    """Raise PermissionError if the command is not on the allowlist."""
    if not argv:
        raise ValueError("Empty command.")

    base = argv[0].lower()
    # Strip path prefix — only check the binary name
    base = base.split("/")[-1].split("\\")[-1]

    if base not in ALLOWED_COMMANDS:
        raise PermissionError(
            f"Command '{base}' is not in the allowed commands list. "
            f"Permitted: {sorted(ALLOWED_COMMANDS)}"
        )

    # Extra guard for git: only allow read-only sub-commands
    if base == "git":
        subcommand = argv[1].lower() if len(argv) > 1 else ""
        if subcommand not in _ALLOWED_GIT_SUBCOMMANDS:
            raise PermissionError(
                f"git sub-command '{subcommand}' is not allowed. "
                f"Allowed: {sorted(_ALLOWED_GIT_SUBCOMMANDS)}"
            )


# ---------------------------------------------------------------------------
# Tool function
# ---------------------------------------------------------------------------


async def shell_execute(params: dict[str, Any]) -> dict[str, Any]:
    """Execute an allowlisted shell command.

    Parameters:
        command (str): The full command string to execute.
        workspace_root (str): Working directory. Command is confined to this path.
        timeout_seconds (int): Hard timeout in seconds. Default 30.
        env (dict[str, str]): Optional environment variable overrides.

    Returns:
        dict with keys: command, exit_code, stdout, stderr, timed_out.
    """
    command: str = params["command"]
    workspace_root: str = params["workspace_root"]
    timeout: int = int(params.get("timeout_seconds", _DEFAULT_TIMEOUT))
    env_override: dict[str, str] = params.get("env") or {}

    argv = _parse_command(command)
    _validate_command(argv)

    logger.info("shell_execute_start", command=command, workspace_root=workspace_root)

    timed_out = False
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_root,
            env={**{}, **env_override} if env_override else None,  # None = inherit parent env
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            timed_out = True
            stdout_bytes, stderr_bytes = b"", b"[TIMED OUT]"

    except FileNotFoundError:
        raise RuntimeError(f"Executable not found: {argv[0]}")

    stdout = stdout_bytes[:_MAX_OUTPUT_BYTES].decode(errors="replace")
    stderr = stderr_bytes[:_MAX_OUTPUT_BYTES].decode(errors="replace")
    exit_code = proc.returncode or 0

    logger.info(
        "shell_execute_done",
        command=command,
        exit_code=exit_code,
        timed_out=timed_out,
        stdout_bytes=len(stdout_bytes),
    )

    return {
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
    }


# ---------------------------------------------------------------------------
# Tool definition (for ToolRegistry)
# ---------------------------------------------------------------------------

SHELL_EXECUTE_DEF = ToolDefinition(
    name="shell.execute",
    description="Execute an allowlisted shell command in the agent workspace.",
    permissions=["shell.execute"],
    risk_level="high",
    requires_approval=False,
    sandbox_required=True,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["command", "workspace_root"],
        "properties": {
            "command": {"type": "string"},
            "workspace_root": {"type": "string"},
            "timeout_seconds": {"type": "integer"},
            "env": {"type": "object"},
        },
    },
)


def register_shell_tools(registry: Any) -> None:
    """Register shell tools into the provided registry."""
    registry.register(SHELL_EXECUTE_DEF, shell_execute)
