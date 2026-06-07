"""Sandbox Execution — Docker-based isolation for tool calls.

Isolation tiers (matches ToolRegistry risk scoring):
    process          (risk 0–25)  — asyncio subprocess with resource limits
    container        (risk 26–60) — ephemeral Docker container, auto-removed
    isolated_container (risk 61–85) — Docker + network=none + read-only FS
    blocked          (risk 86–100) — requires human approval before execution

This module provides:
- ``SandboxConfig`` — per-run configuration (image, limits, network)
- ``SandboxResult`` — captured output from a sandboxed execution
- ``run_in_sandbox()`` — async entry-point that dispatches to the correct tier
- ``run_in_process()`` — low-isolation subprocess runner
- ``run_in_container()`` — Docker container runner (standard / isolated)

Docker availability is detected at import time.  If Docker is unavailable the
container tiers fall back to raising ``SandboxUnavailableError`` so callers
can handle it without crashing the whole runtime.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Docker availability probe
# ---------------------------------------------------------------------------

try:
    import docker as _docker_module  # type: ignore[import]

    _DOCKER_CLIENT = _docker_module.from_env()
    _DOCKER_CLIENT.ping()
    DOCKER_AVAILABLE = True
except Exception:  # pragma: no cover
    DOCKER_AVAILABLE = False
    _DOCKER_CLIENT = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SandboxUnavailableError(RuntimeError):
    """Raised when the requested isolation tier is not available."""


class SandboxSecurityError(PermissionError):
    """Raised when a request is blocked by sandbox policy."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SandboxConfig:
    """Configuration for a sandboxed execution.

    Attributes:
        isolation_tier: One of ``process | container | isolated_container | blocked``.
        docker_image:   Docker image to use for container tiers.
        command:        Shell command or argv list to execute inside the sandbox.
        environment:    Environment variables injected into the container.
        timeout_seconds: Hard execution timeout.
        memory_limit_mb: Container memory cap (container tiers only).
        cpu_quota:       Docker CPU quota (1e5 = 1 CPU core).
        workspace_mount: Host path to mount as ``/workspace`` (read-only by default).
        allow_network:   Allow outbound network from the container.
        run_id:          Unique identifier for this execution (auto-generated).
    """

    isolation_tier: str  # process | container | isolated_container | blocked
    command: list[str] | str
    docker_image: str = "python:3.12-slim"
    environment: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 60
    memory_limit_mb: int = 256
    cpu_quota: int = 50_000  # 0.5 CPU
    workspace_mount: str | None = None
    allow_network: bool = False
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class SandboxResult:
    """Result from a sandboxed execution."""

    run_id: str
    isolation_tier: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    elapsed_seconds: float
    timed_out: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


async def run_in_sandbox(config: SandboxConfig) -> SandboxResult:
    """Dispatch execution to the correct isolation tier.

    Parameters:
        config: ``SandboxConfig`` describing what to run and at what isolation.

    Returns:
        ``SandboxResult`` capturing stdout/stderr/exit_code.

    Raises:
        SandboxSecurityError: If tier is ``blocked``.
        SandboxUnavailableError: If Docker is required but unavailable.
    """
    tier = config.isolation_tier

    logger.info(
        "sandbox.dispatch",
        run_id=config.run_id,
        tier=tier,
        timeout=config.timeout_seconds,
    )

    if tier == "blocked":
        raise SandboxSecurityError(
            f"Execution blocked — risk score requires human approval (run_id={config.run_id})"
        )

    if tier == "process":
        return await run_in_process(config)

    if tier in ("container", "isolated_container"):
        if not DOCKER_AVAILABLE:
            raise SandboxUnavailableError(
                "Docker is not available on this host — cannot run container tier"
            )
        return await run_in_container(config)

    raise ValueError(f"Unknown isolation tier: {tier!r}")


# ---------------------------------------------------------------------------
# Process tier (low isolation)
# ---------------------------------------------------------------------------


async def run_in_process(config: SandboxConfig) -> SandboxResult:
    """Run command in a subprocess with resource limits.

    Uses ``asyncio.create_subprocess_exec`` (never ``shell=True``).
    stdout/stderr are capped at 256 KB each.
    """
    start = time.monotonic()
    argv = _normalise_argv(config.command)
    env = config.environment if config.environment else None

    proc: asyncio.subprocess.Process | None = None
    timed_out = False
    stdout_bytes = b""
    stderr_bytes = b""
    exit_code = -1

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=config.timeout_seconds,
            )
            exit_code = proc.returncode or 0
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            exit_code = -1

    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - start
        return SandboxResult(
            run_id=config.run_id,
            isolation_tier="process",
            success=False,
            stdout="",
            stderr="",
            exit_code=-1,
            elapsed_seconds=round(elapsed, 3),
            error=str(exc),
        )

    elapsed = time.monotonic() - start
    _MAX = 256 * 1024
    success = exit_code == 0 and not timed_out

    logger.info(
        "sandbox.process.done",
        run_id=config.run_id,
        exit_code=exit_code,
        elapsed=round(elapsed, 3),
        timed_out=timed_out,
    )

    return SandboxResult(
        run_id=config.run_id,
        isolation_tier="process",
        success=success,
        stdout=stdout_bytes[:_MAX].decode("utf-8", errors="replace"),
        stderr=stderr_bytes[:_MAX].decode("utf-8", errors="replace"),
        exit_code=exit_code,
        elapsed_seconds=round(elapsed, 3),
        timed_out=timed_out,
    )


# ---------------------------------------------------------------------------
# Container tier (medium / high isolation)
# ---------------------------------------------------------------------------


async def run_in_container(config: SandboxConfig) -> SandboxResult:
    """Run command inside an ephemeral Docker container.

    Container is always auto-removed after execution.
    For ``isolated_container`` tier: network is disabled and FS is read-only.
    """
    start = time.monotonic()
    isolated = config.isolation_tier == "isolated_container"
    container_name = f"cortexflow-sandbox-{config.run_id[:8]}"

    argv = _normalise_argv(config.command)
    cmd_str = " ".join(shlex.quote(a) for a in argv) if isinstance(argv, list) else argv

    # Build Docker run kwargs
    run_kwargs: dict[str, Any] = {
        "image": config.docker_image,
        "command": cmd_str,
        "name": container_name,
        "detach": True,
        "auto_remove": False,  # we remove manually after log capture
        "mem_limit": f"{config.memory_limit_mb}m",
        "cpu_quota": config.cpu_quota,
        "environment": config.environment,
        "read_only": isolated,
        "network_disabled": isolated or not config.allow_network,
        "security_opt": ["no-new-privileges"],
    }

    if config.workspace_mount:
        run_kwargs["volumes"] = {config.workspace_mount: {"bind": "/workspace", "mode": "ro"}}

    # Run the container in a thread pool to avoid blocking the event loop.
    # asyncio.get_running_loop() is required in Python 3.10+ inside async functions.
    loop = asyncio.get_running_loop()
    timed_out = False
    exit_code = -1
    stdout_bytes = b""
    stderr_bytes = b""

    try:
        container = await loop.run_in_executor(
            None,
            lambda: _DOCKER_CLIENT.containers.run(**run_kwargs),
        )

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: container.wait()),
                timeout=config.timeout_seconds,
            )
            exit_code = result.get("StatusCode", -1)
        except asyncio.TimeoutError:
            timed_out = True
            exit_code = -1
            try:
                await loop.run_in_executor(None, lambda: container.kill())
            except Exception:  # noqa: BLE001
                pass
        finally:
            # Always collect logs and remove — even if kill() raised (BUG-005).
            # Separate stdout/stderr calls so stderr is not discarded (BUG-011).
            try:
                stdout_bytes = await loop.run_in_executor(
                    None, lambda: container.logs(stdout=True, stderr=False)
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                stderr_bytes = await loop.run_in_executor(
                    None, lambda: container.logs(stdout=False, stderr=True)
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                await loop.run_in_executor(None, lambda: container.remove(force=True))
            except Exception:  # noqa: BLE001
                pass

    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - start
        logger.error(
            "sandbox.container.error",
            run_id=config.run_id,
            error=str(exc),
        )
        return SandboxResult(
            run_id=config.run_id,
            isolation_tier=config.isolation_tier,
            success=False,
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            elapsed_seconds=round(elapsed, 3),
            error=str(exc),
        )

    elapsed = time.monotonic() - start
    _MAX = 256 * 1024
    success = exit_code == 0 and not timed_out

    logger.info(
        "sandbox.container.done",
        run_id=config.run_id,
        tier=config.isolation_tier,
        exit_code=exit_code,
        elapsed=round(elapsed, 3),
        timed_out=timed_out,
    )

    return SandboxResult(
        run_id=config.run_id,
        isolation_tier=config.isolation_tier,
        success=success,
        stdout=stdout_bytes[:_MAX].decode("utf-8", errors="replace"),
        stderr=stderr_bytes[:_MAX].decode("utf-8", errors="replace"),
        exit_code=exit_code,
        elapsed_seconds=round(elapsed, 3),
        timed_out=timed_out,
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _normalise_argv(command: list[str] | str) -> list[str]:
    """Ensure command is a list of strings (never passed to shell=True)."""
    if isinstance(command, list):
        return command
    return shlex.split(command, posix=True)
