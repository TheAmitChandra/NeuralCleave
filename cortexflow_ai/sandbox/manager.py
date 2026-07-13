"""SandboxManager — unified interface for creating and using sandboxes.

:class:`SandboxManager` wraps a :class:`~cortexflow_ai.sandbox.base.Sandbox`
and exposes convenience factory methods that read configuration or accept
keyword arguments.

Usage::

    # Local subprocess sandbox (default)
    mgr = SandboxManager.local()
    result = await mgr.execute("echo hello")

    # Docker sandbox
    mgr = SandboxManager.docker(image="python:3.12-slim", network="bridge")
    result = await mgr.execute("pip show pip")

    # SSH sandbox
    mgr = SandboxManager.ssh(host="192.168.1.10", username="ci")
    result = await mgr.execute("uname -a")

    # From a config dict
    mgr = SandboxManager.from_config({"backend": "docker", "image": "ubuntu:22.04"})
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cortexflow_ai.sandbox.base import Sandbox, SandboxResult

logger = logging.getLogger(__name__)


class SandboxManager:
    """High-level façade over a :class:`~cortexflow_ai.sandbox.base.Sandbox`.

    Args:
        sandbox: The concrete sandbox instance to delegate to.
    """

    def __init__(self, sandbox: "Sandbox") -> None:
        self._sandbox = sandbox

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def local(
        cls,
        *,
        work_dir: Path | str | None = None,
        max_output_bytes: int = 50 * 1024,
        default_timeout: float = 30.0,
    ) -> "SandboxManager":
        """Create a :class:`~cortexflow_ai.sandbox.local.LocalSandbox` manager."""
        from cortexflow_ai.sandbox.local import LocalSandbox

        return cls(
            LocalSandbox(
                work_dir=work_dir,
                max_output_bytes=max_output_bytes,
                default_timeout=default_timeout,
            )
        )

    @classmethod
    def docker(
        cls,
        *,
        image: str = "python:3.12-slim",
        network: str = "none",
        memory: str = "256m",
        cpus: float = 0.5,
        default_timeout: float = 30.0,
        work_dir: Path | str | None = None,
        extra_flags: list[str] | None = None,
    ) -> "SandboxManager":
        """Create a :class:`~cortexflow_ai.sandbox.docker.DockerSandbox` manager."""
        from cortexflow_ai.sandbox.docker import DockerSandbox

        return cls(
            DockerSandbox(
                image=image,
                network=network,
                memory=memory,
                cpus=cpus,
                default_timeout=default_timeout,
                work_dir=work_dir,
                extra_flags=extra_flags,
            )
        )

    @classmethod
    def ssh(
        cls,
        *,
        host: str,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        key_path: str | Path | None = None,
        known_hosts: str | None = None,
        default_timeout: float = 30.0,
    ) -> "SandboxManager":
        """Create an :class:`~cortexflow_ai.sandbox.ssh.SSHSandbox` manager."""
        from cortexflow_ai.sandbox.ssh import SSHSandbox

        return cls(
            SSHSandbox(
                host=host,
                port=port,
                username=username,
                password=password,
                key_path=key_path,
                known_hosts=known_hosts,
                default_timeout=default_timeout,
            )
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SandboxManager":
        """Create a manager from a plain-dict config.

        The ``backend`` key selects the sandbox type (``"local"``,
        ``"docker"``, or ``"ssh"``).  All other keys are forwarded as
        keyword arguments to the corresponding factory method.

        Raises:
            ValueError: If ``backend`` is missing or unrecognised.
        """
        cfg = dict(config)
        backend = cfg.pop("backend", "local")

        if backend == "local":
            return cls.local(**cfg)
        if backend == "docker":
            return cls.docker(**cfg)
        if backend == "ssh":
            host = cfg.pop("host", None)
            if not host:
                raise ValueError("SSHSandbox requires 'host' in config")
            return cls.ssh(host=host, **cfg)

        raise ValueError(
            f"Unknown sandbox backend '{backend}'. "
            "Choose 'local', 'docker', or 'ssh'."
        )

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    async def execute(
        self,
        command: str,
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float | None = None,
        input_data: bytes | None = None,
    ) -> "SandboxResult":
        """Execute *command* in the configured sandbox."""
        return await self._sandbox.execute(
            command,
            env=env,
            cwd=cwd,
            timeout=timeout,
            input_data=input_data,
        )

    async def ping(self) -> bool:
        """Return ``True`` if the backend is reachable."""
        return await self._sandbox.ping()

    def info(self) -> dict[str, Any]:
        """Return backend info dict."""
        return self._sandbox.info()

    @property
    def backend(self) -> str:
        """Name of the active backend (``"local"``, ``"docker"``, ``"ssh"``)."""
        return self._sandbox.backend_name

    @property
    def sandbox(self) -> "Sandbox":
        """The wrapped :class:`~cortexflow_ai.sandbox.base.Sandbox` instance."""
        return self._sandbox
