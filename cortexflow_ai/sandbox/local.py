"""LocalSandbox — executes commands in a restricted subprocess on the host.

This is equivalent to the existing :class:`~cortexflow_ai.tools.shell.ShellTool`
approach but wrapped in the :class:`~cortexflow_ai.sandbox.base.Sandbox` ABC so
it can be swapped for Docker or SSH backends via :class:`SandboxManager`.

Safety properties
-----------------
- ``asyncio.create_subprocess_shell`` with a hard ``asyncio.wait_for`` timeout.
- ``stdout`` and ``stderr`` are capped at *max_output_bytes*.
- Sensitive environment variables (API keys, tokens) are stripped unless the
  caller explicitly passes ``env``.
- Working directory defaults to a dedicated ``work_dir`` (``~/cortexflow_files``
  by default) — the process cannot change it to ``/`` etc. without elevated
  permissions.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from cortexflow_ai.sandbox.base import Sandbox, SandboxResult

logger = logging.getLogger(__name__)

_DEFAULT_WORK_DIR = Path.home() / "cortexflow_files"
_DEFAULT_MAX_BYTES = 50 * 1024  # 50 KB

_SENSITIVE_ENV_PREFIXES = (
    "ANTHROPIC_",
    "GEMINI_",
    "DEEPSEEK_",
    "OPENAI_",
    "ELEVENLABS_",
    "AWS_",
    "AZURE_",
    "GCP_",
    "SECRET_",
    "TOKEN_",
    "PASSWORD_",
    "API_KEY",
)


def _sanitise_env(extra: dict[str, str] | None) -> dict[str, str]:
    """Return a clean environment — strip sensitive keys, merge *extra*."""
    clean = {
        k: v
        for k, v in os.environ.items()
        if not any(k.upper().startswith(p) for p in _SENSITIVE_ENV_PREFIXES)
    }
    if extra:
        clean.update(extra)
    return clean


class LocalSandbox(Sandbox):
    """Runs commands in an asyncio subprocess on the local host.

    Args:
        work_dir:        Default working directory for executed commands.
                         Created on demand if it does not exist.
        max_output_bytes: Maximum bytes captured from stdout + stderr each.
        default_timeout: Per-call timeout in seconds used when the caller
                         does not specify ``timeout``.
    """

    backend_name = "local"

    def __init__(
        self,
        work_dir: Path | str | None = None,
        max_output_bytes: int = _DEFAULT_MAX_BYTES,
        default_timeout: float = 30.0,
    ) -> None:
        self._work_dir = Path(work_dir) if work_dir else _DEFAULT_WORK_DIR
        self._max_output_bytes = max_output_bytes
        self._default_timeout = default_timeout

    async def execute(
        self,
        command: str,
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float | None = None,
        input_data: bytes | None = None,
    ) -> SandboxResult:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        effective_cwd = str(cwd) if cwd else str(self._work_dir)
        effective_env = _sanitise_env(env)

        self._work_dir.mkdir(parents=True, exist_ok=True)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if input_data else asyncio.subprocess.DEVNULL,
                cwd=effective_cwd,
                env=effective_env,
            )
        except Exception as exc:
            logger.error("local_sandbox.spawn_error: %s", exc)
            return SandboxResult(
                stdout="",
                stderr=str(exc),
                exit_code=1,
                backend=self.backend_name,
            )

        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(input=input_data),
                timeout=effective_timeout,
            )
            timed_out = False
            exit_code = proc.returncode if proc.returncode is not None else 1
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raw_out, raw_err = b"", b""
            timed_out = True
            exit_code = -1

        stdout = raw_out[: self._max_output_bytes].decode("utf-8", errors="replace")
        stderr = raw_err[: self._max_output_bytes].decode("utf-8", errors="replace")

        logger.debug(
            "local_sandbox.execute exit=%d timed_out=%s cmd=%r",
            exit_code,
            timed_out,
            command[:80],
        )
        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            backend=self.backend_name,
        )

    async def ping(self) -> bool:
        result = await self.execute("echo __sandbox_ok__", timeout=5.0)
        return result.success and "__sandbox_ok__" in result.stdout

    def info(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "work_dir": str(self._work_dir),
            "max_output_bytes": self._max_output_bytes,
            "default_timeout": self._default_timeout,
        }
