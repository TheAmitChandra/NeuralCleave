"""DockerSandbox — executes commands inside an ephemeral Docker container.

Each :meth:`execute` call spawns a fresh ``docker run --rm`` container so
there is no state leakage between calls.  The container is:

- **Network-isolated** — ``--network none`` by default; override with
  ``network="bridge"`` for commands that need internet access.
- **Memory-capped** — ``--memory <memory>`` prevents OOM on the host.
- **CPU-capped** — ``--cpus <cpus>`` limits CPU share.
- **Privilege-dropped** — ``--security-opt no-new-privileges``.
- **Ephemeral** — ``--rm`` removes the container on exit.

Requires Docker to be installed and the ``docker`` CLI to be on ``PATH``.
Use :meth:`ping` to verify availability before scheduling work.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from neuralcleave.sandbox.base import Sandbox, SandboxResult

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "python:3.12-slim"
_DEFAULT_MAX_BYTES = 50 * 1024


class DockerSandbox(Sandbox):
    """Runs commands inside a fresh Docker container on each call.

    Args:
        image:           Docker image to use (must be pullable from the host).
        network:         Docker network mode. ``"none"`` disables all networking.
        memory:          Memory limit string accepted by Docker (e.g. ``"256m"``).
        cpus:            CPU share (e.g. ``0.5`` = half a core).
        default_timeout: Seconds before the container is killed.
        work_dir:        Host directory mounted at ``/workspace`` inside the
                         container. Defaults to ``~/NeuralCleave_files``.
        max_output_bytes: Maximum bytes captured from stdout + stderr each.
        extra_flags:     Additional ``docker run`` flags appended verbatim.
    """

    backend_name = "docker"

    def __init__(
        self,
        image: str = _DEFAULT_IMAGE,
        network: str = "none",
        memory: str = "256m",
        cpus: float = 0.5,
        default_timeout: float = 30.0,
        work_dir: Path | str | None = None,
        max_output_bytes: int = _DEFAULT_MAX_BYTES,
        extra_flags: list[str] | None = None,
    ) -> None:
        self._image = image
        self._network = network
        self._memory = memory
        self._cpus = cpus
        self._default_timeout = default_timeout
        self._work_dir = Path(work_dir) if work_dir else Path.home() / "NeuralCleave_files"
        self._max_output_bytes = max_output_bytes
        self._extra_flags = extra_flags or []

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
        if not shutil.which("docker"):
            return SandboxResult(
                stdout="",
                stderr="docker executable not found — install Docker to use DockerSandbox",
                exit_code=1,
                backend=self.backend_name,
            )

        effective_timeout = timeout if timeout is not None else self._default_timeout
        self._work_dir.mkdir(parents=True, exist_ok=True)

        docker_cmd = self._build_command(command, env, cwd)

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if input_data else asyncio.subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.error("docker_sandbox.spawn_error: %s", exc)
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
            "docker_sandbox.execute exit=%d timed_out=%s image=%s",
            exit_code,
            timed_out,
            self._image,
        )
        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            backend=self.backend_name,
            metadata={"image": self._image},
        )

    async def ping(self) -> bool:
        """Return ``True`` if ``docker info`` succeeds (Docker daemon is running)."""
        if not shutil.which("docker"):
            return False
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=10.0)
            return proc.returncode == 0
        except Exception:
            return False

    def info(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "image": self._image,
            "network": self._network,
            "memory": self._memory,
            "cpus": self._cpus,
            "work_dir": str(self._work_dir),
            "default_timeout": self._default_timeout,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_command(
        self,
        command: str,
        env: dict[str, str] | None,
        cwd: str | None,
    ) -> list[str]:
        cmd = [
            "docker", "run", "--rm",
            "--network", self._network,
            "--memory", self._memory,
            "--cpus", str(self._cpus),
            "--security-opt", "no-new-privileges",
            "-v", f"{self._work_dir}:/workspace",
            "-w", cwd or "/workspace",
        ]
        if env:
            for k, v in env.items():
                cmd += ["-e", f"{k}={v}"]
        cmd.extend(self._extra_flags)
        cmd += [self._image, "sh", "-c", command]
        return cmd
