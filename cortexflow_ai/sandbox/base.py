"""Sandbox abstract base class and shared result type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxResult:
    """Result of a single sandbox command execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    backend: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """``True`` when the command exited 0 and did not time out."""
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "backend": self.backend,
            "success": self.success,
        }


class Sandbox(ABC):
    """Abstract execution sandbox.

    Subclasses implement :meth:`execute` and :meth:`ping` for a specific
    backend (local subprocess, Docker, SSH, …).

    Class attributes:
        backend_name: Short identifier shown in ``cortex sandbox status``.
    """

    backend_name: str = "abstract"

    @abstractmethod
    async def execute(
        self,
        command: str,
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float | None = None,
        input_data: bytes | None = None,
    ) -> SandboxResult:
        """Run *command* in the sandbox and return a :class:`SandboxResult`.

        Args:
            command:    Shell command string to execute.
            env:        Extra environment variables to pass into the sandbox.
            cwd:        Working directory inside the sandbox.
            timeout:    Per-call timeout override in seconds.
            input_data: Optional stdin bytes.

        Returns:
            :class:`SandboxResult` — never raises; errors appear in
            ``result.stderr`` with a non-zero ``exit_code``.
        """
        ...

    @abstractmethod
    async def ping(self) -> bool:
        """Return ``True`` if the backend is reachable and operational."""
        ...

    def info(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict describing this sandbox."""
        return {"backend": self.backend_name}
