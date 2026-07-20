"""SSHSandbox — executes commands on a remote host over SSH.

Execution is forwarded to a remote machine, giving full isolation from the
local host while keeping the gateway itself lightweight.

Backend priority
----------------
1. **asyncssh** — pure-Python async SSH; used if ``pip install asyncssh`` is
   present.  Gives native async I/O with no subprocess overhead.
2. **ssh CLI fallback** — uses the system ``ssh`` binary via
   ``asyncio.create_subprocess_exec`` when asyncssh is not available.

Authentication
--------------
Supports password, private-key file (``key_path``), and SSH agent (when
neither password nor key_path is given).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from neuralcleave.sandbox.base import Sandbox, SandboxResult

logger = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 50 * 1024


class SSHSandbox(Sandbox):
    """Runs commands on a remote host via SSH.

    Args:
        host:            Hostname or IP of the remote machine.
        port:            SSH port (default 22).
        username:        SSH username. Defaults to the current user.
        password:        SSH password (prefer key-based auth for security).
        key_path:        Path to a private key file (e.g. ``~/.ssh/id_ed25519``).
        known_hosts:     Path to a known_hosts file. ``None`` disables host-key
                         checking (insecure; only for dev/test environments).
        default_timeout: Per-call timeout in seconds.
        max_output_bytes: Cap on stdout/stderr bytes captured per call.
    """

    backend_name = "ssh"

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        key_path: str | Path | None = None,
        known_hosts: str | None = None,
        default_timeout: float = 30.0,
        max_output_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._key_path = Path(key_path) if key_path else None
        self._known_hosts = known_hosts
        self._default_timeout = default_timeout
        self._max_output_bytes = max_output_bytes

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        full_command = self._wrap_command(command, env, cwd)

        try:
            return await asyncio.wait_for(
                self._execute_asyncssh(full_command, input_data),
                timeout=effective_timeout,
            )
        except ImportError:
            pass
        except asyncio.TimeoutError:
            return SandboxResult(
                stdout="", stderr="SSH command timed out",
                exit_code=-1, timed_out=True, backend=self.backend_name,
            )
        except Exception as exc:
            logger.debug("ssh_sandbox.asyncssh_error: %s — falling back to CLI", exc)

        # Fall back to the ssh CLI binary
        try:
            return await asyncio.wait_for(
                self._execute_cli(full_command, input_data),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            return SandboxResult(
                stdout="", stderr="SSH command timed out",
                exit_code=-1, timed_out=True, backend=self.backend_name,
            )
        except Exception as exc:
            return SandboxResult(
                stdout="", stderr=str(exc),
                exit_code=1, backend=self.backend_name,
            )

    async def ping(self) -> bool:
        """Return ``True`` if the remote host is reachable over SSH."""
        result = await self.execute("echo __ssh_ok__", timeout=10.0)
        return result.success and "__ssh_ok__" in result.stdout

    def info(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "host": self._host,
            "port": self._port,
            "username": self._username or "(current user)",
            "key_path": str(self._key_path) if self._key_path else None,
            "default_timeout": self._default_timeout,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _wrap_command(
        self,
        command: str,
        env: dict[str, str] | None,
        cwd: str | None,
    ) -> str:
        parts: list[str] = []
        if env:
            exports = " ".join(f"export {k}={shlex_quote(v)};" for k, v in env.items())
            parts.append(exports)
        if cwd:
            parts.append(f"cd {shlex_quote(cwd)} &&")
        parts.append(command)
        return " ".join(parts)

    async def _execute_asyncssh(
        self,
        command: str,
        input_data: bytes | None,
    ) -> SandboxResult:
        import asyncssh  # type: ignore[import]

        connect_kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "known_hosts": self._known_hosts,
        }
        if self._username:
            connect_kwargs["username"] = self._username
        if self._password:
            connect_kwargs["password"] = self._password
        if self._key_path:
            connect_kwargs["client_keys"] = [str(self._key_path)]

        async with asyncssh.connect(**connect_kwargs) as conn:
            stdin_str = input_data.decode("utf-8", errors="replace") if input_data else None
            result = await conn.run(command, input=stdin_str)

        stdout = (result.stdout or "")[: self._max_output_bytes]
        stderr = (result.stderr or "")[: self._max_output_bytes]
        exit_code = result.exit_status if result.exit_status is not None else 0
        return SandboxResult(
            stdout=stdout, stderr=stderr, exit_code=exit_code,
            backend=self.backend_name,
        )

    async def _execute_cli(
        self,
        command: str,
        input_data: bytes | None,
    ) -> SandboxResult:
        if not shutil.which("ssh"):
            raise RuntimeError("ssh CLI not found and asyncssh is not installed")

        ssh_args = self._build_cli_args()
        ssh_args += [self._host, command]

        proc = await asyncio.create_subprocess_exec(
            *ssh_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_data else asyncio.subprocess.DEVNULL,
        )
        raw_out, raw_err = await proc.communicate(input=input_data)
        exit_code = proc.returncode if proc.returncode is not None else 1

        return SandboxResult(
            stdout=raw_out[: self._max_output_bytes].decode("utf-8", errors="replace"),
            stderr=raw_err[: self._max_output_bytes].decode("utf-8", errors="replace"),
            exit_code=exit_code,
            backend=self.backend_name,
        )

    def _build_cli_args(self) -> list[str]:
        args = ["ssh", "-p", str(self._port), "-o", "BatchMode=yes"]
        if self._known_hosts is None:
            args += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]
        elif self._known_hosts:
            args += ["-o", f"UserKnownHostsFile={self._known_hosts}"]
        if self._key_path:
            args += ["-i", str(self._key_path)]
        if self._username:
            args += ["-l", self._username]
        return args


def shlex_quote(s: str) -> str:
    """Minimal shell quoting for values injected into remote commands."""
    return "'" + s.replace("'", "'\"'\"'") + "'"
