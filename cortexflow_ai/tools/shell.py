"""Sandboxed shell execution tool.

Runs commands as a list of tokens (never via a shell interpreter), which means
shell metacharacters — ``;`` ``&&`` ``|`` ``$()`` backtick — are **never**
interpreted.  They are passed verbatim as arguments to the program, so command
injection is architecturally impossible when ``shell=False`` is used.

A configurable allowlist (on by default) restricts which programs the agent
may invoke.  Pass ``allowed_commands=None`` to ShellTool to lift the
restriction for trusted, single-user deployments.

Security properties:
  - ``subprocess.run(shell=False)`` always — no shell interpreter is invoked
  - Allowlist on first token (program name, basename, ``.exe`` stripped)
  - Working directory constrained to sandbox root unless workdir_absolute=True
  - Sensitive environment variables (API_KEY, TOKEN, SECRET …) stripped before exec
  - Hard timeout enforced via ``subprocess.run(timeout=N)``
  - Output capped at MAX_OUTPUT_BYTES per stream (stdout + stderr)

Result metadata keys:
  stdout     str  — raw standard output (possibly truncated)
  stderr     str  — raw standard error (possibly truncated)
  exit_code  int | None  — process exit code; None when timed out
  timed_out  bool — True if the process was killed by the timeout
  command    str  — the actual command string that was executed
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from cortexflow_ai.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_SANDBOX: Path = Path.home() / "cortexflow_files"
DEFAULT_TIMEOUT: int = 30
MAX_OUTPUT_BYTES: int = 50_000  # 50 KB per stream

# Conservative default allowlist — programs safe for a personal assistant
_DEFAULT_ALLOWED: frozenset[str] = frozenset({
    # File inspection
    "cat", "cut", "file", "find", "grep", "head", "ls", "rg", "sed",
    "sort", "stat", "tail", "tr", "uniq", "wc",
    # Navigation / system info
    "date", "df", "dir", "du", "echo", "env", "hostname",
    "printenv", "pwd", "type", "uname", "where", "which", "whoami",
    # Dev tools
    "gh", "git", "pip", "pip3", "python", "python3", "uv",
    # Data / network (read-only)
    "curl", "dig", "jq", "nslookup", "ping", "ss", "wget",
})

# Environment variable name substrings that mark sensitive values to strip
_SENSITIVE_PATTERNS: tuple[str, ...] = (
    "API_KEY", "SECRET", "PASSWORD", "TOKEN", "PRIVATE", "CREDENTIAL",
    "ANTHROPIC", "GEMINI", "OPENAI", "DEEPSEEK", "ELEVENLABS",
)


# ──────────────────────────────────────────────────────────────────────────────
# Tool
# ──────────────────────────────────────────────────────────────────────────────


class ShellTool(Tool):
    """Execute sandboxed shell commands for the agent.

    The tool never uses ``shell=True``, so the command string is split into
    tokens with :func:`shlex.split` and handed directly to the OS.  Shell
    metacharacters are always treated as literal arguments.

    Args:
        sandbox:          Root directory for the working-directory sandbox.
                          Defaults to ``~/cortexflow_files/``.
        allowed_commands: Frozenset of allowed program names (basename, lower,
                          no ``.exe``).  Pass ``None`` to allow any program.
    """

    name = "shell"
    description = (
        "Execute a command on the local system. "
        "Shell metacharacters (; && | $()) are never interpreted — only the "
        "program name and its arguments are passed to the OS. "
        "An allowlist restricts which programs may be run."
    )
    parameters = {
        "command": {
            "type": "str",
            "description": "Command to run, e.g. 'git log --oneline -5' or 'python3 script.py'.",
            "required": True,
        },
        "timeout": {
            "type": "int",
            "description": f"Maximum seconds to wait before killing the process (default {DEFAULT_TIMEOUT}).",
            "required": False,
        },
        "workdir": {
            "type": "str",
            "description": (
                "Working directory as a path relative to the sandbox root. "
                "Omit to use the sandbox root itself."
            ),
            "required": False,
        },
    }
    permissions = ["shell:execute"]

    def __init__(
        self,
        sandbox: Path | str | None = None,
        allowed_commands: frozenset[str] | set[str] | None = _DEFAULT_ALLOWED,
    ) -> None:
        self._sandbox = (
            Path(sandbox).expanduser() if sandbox is not None else DEFAULT_SANDBOX.expanduser()
        )
        # None → unrestricted; frozenset → allowlist enforced
        self._allowed: frozenset[str] | None = (
            frozenset(c.lower() for c in allowed_commands)
            if allowed_commands is not None
            else None
        )

    # ──────────────────────────────────────────────────────────────────────────

    async def execute(
        self,
        command: str,
        timeout: int = DEFAULT_TIMEOUT,
        workdir: str | None = None,
        **_: Any,
    ) -> ToolResult:
        stripped = (command or "").strip()
        if not stripped:
            return ToolResult(tool=self.name, output=None, error="Command must not be empty.")

        # Parse into token list — never passes to shell
        try:
            tokens = shlex.split(stripped)
        except ValueError as exc:
            return ToolResult(tool=self.name, output=None, error=f"Invalid command syntax: {exc}")

        if not tokens:
            return ToolResult(tool=self.name, output=None, error="Command must not be empty.")

        # Allowlist check on program name (basename, lowercase, .exe stripped)
        if not self._is_allowed(tokens[0]):
            prog = Path(tokens[0]).name
            return ToolResult(
                tool=self.name,
                output=None,
                error=(
                    f"Program {prog!r} is not in the allowed list. "
                    "Use ShellTool(allowed_commands=None) to allow any command."
                ),
            )

        # Resolve working directory within sandbox
        try:
            cwd = self._resolve_workdir(workdir)
        except ValueError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        env = _sanitize_env()

        try:
            return await asyncio.to_thread(
                self._run_sync, tokens, cwd, int(timeout), env
            )
        except Exception as exc:
            logger.error("shell.execute unhandled error: %s", exc)
            return ToolResult(tool=self.name, output=None, error=str(exc))

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _is_allowed(self, program: str) -> bool:
        if self._allowed is None:
            return True
        name = Path(program).name.lower()
        if name.endswith(".exe"):
            name = name[:-4]
        return name in self._allowed

    def _resolve_workdir(self, workdir: str | None) -> Path:
        if workdir is None:
            self._sandbox.mkdir(parents=True, exist_ok=True)
            return self._sandbox
        p = Path(workdir)
        if p.is_absolute():
            raise ValueError(f"Absolute workdir paths are not allowed: {workdir!r}")
        resolved = (self._sandbox / p).resolve()
        try:
            resolved.relative_to(self._sandbox.resolve())
        except ValueError:
            raise ValueError(f"Workdir traversal outside sandbox is not allowed: {workdir!r}")
        if not resolved.exists():
            raise ValueError(f"Workdir does not exist: {workdir!r}")
        return resolved

    def _run_sync(
        self,
        tokens: list[str],
        cwd: Path,
        timeout: int,
        env: dict[str, str],
    ) -> ToolResult:
        timed_out = False
        stdout_text = ""
        stderr_text = ""
        exit_code: int | None = None

        try:
            proc = subprocess.run(
                tokens,
                capture_output=True,
                cwd=str(cwd),
                timeout=timeout,
                env=env,
            )
            stdout_text = _truncate(proc.stdout.decode("utf-8", errors="replace"), MAX_OUTPUT_BYTES)
            stderr_text = _truncate(proc.stderr.decode("utf-8", errors="replace"), MAX_OUTPUT_BYTES)
            exit_code = proc.returncode

        except subprocess.TimeoutExpired:
            timed_out = True

        except FileNotFoundError:
            return ToolResult(
                tool=self.name,
                output=None,
                error=f"Program not found: {tokens[0]!r}",
            )

        # Build human-readable output block
        parts: list[str] = []
        if stdout_text:
            parts.append(stdout_text.rstrip())
        if stderr_text:
            parts.append(f"[stderr]\n{stderr_text.rstrip()}")
        if timed_out:
            parts.append(f"[timed out after {timeout}s]")
        output = "\n".join(parts) if parts else "(no output)"

        # Determine error string
        if timed_out:
            error: str | None = f"Command timed out after {timeout}s."
        elif exit_code != 0:
            error = f"Exit code {exit_code}." + (f"\n{stderr_text.rstrip()}" if stderr_text else "")
        else:
            error = None

        logger.info(
            "shell.run cmd=%r exit_code=%s timed_out=%s",
            " ".join(tokens),
            exit_code,
            timed_out,
        )

        return ToolResult(
            tool=self.name,
            output=output,
            error=error,
            metadata={
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "command": " ".join(tokens),
            },
        )


# ──────────────────────────────────────────────────────────────────────────────
# Module-level helpers
# ──────────────────────────────────────────────────────────────────────────────


def _truncate(text: str, limit: int) -> str:
    """Return text unchanged if within *limit* bytes; otherwise truncate with notice."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="replace") + f"\n[truncated at {limit} bytes]"


def _sanitize_env() -> dict[str, str]:
    """Return os.environ with sensitive keys removed and UTF-8 I/O enforced."""
    upper_pats = tuple(p.upper() for p in _SENSITIVE_PATTERNS)
    env = {k: v for k, v in os.environ.items() if not any(p in k.upper() for p in upper_pats)}
    # Force UTF-8 stdout/stderr on Windows (default is CP1252); harmless on POSIX.
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env
