"""MCP server subprocess lifecycle management.

The :class:`McpServerProcess` tracks a single spawned MCP stdio server
subprocess.  The gateway spawns one when ``POST /api/v1/mcp/spawn`` is
called and keeps it alive until ``DELETE /api/v1/mcp/server`` is called or
the gateway shuts down.

Only one subprocess is tracked at a time; spawning again when one is already
running returns the existing PID without starting a second process.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


class McpServerProcess:
    """Manages the lifecycle of a single MCP stdio server subprocess.

    The subprocess is created via :func:`subprocess.Popen` so the gateway
    process can track and terminate it cleanly.  The stdio pipes are opened
    so the server reads from its stdin and writes to its stdout, but the
    gateway does not read from them (MCP clients connect directly to the
    subprocess).
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None

    @property
    def pid(self) -> int | None:
        if self._proc is None:
            return None
        if self._proc.poll() is not None:
            return None
        return self._proc.pid

    @property
    def is_running(self) -> bool:
        return self.pid is not None

    def spawn(self) -> int:
        """Start the MCP server subprocess.  Returns the PID.

        If a process is already running its PID is returned without
        starting a new one.
        """
        if self.is_running:
            assert self._proc is not None
            return self._proc.pid

        self._proc = subprocess.Popen(
            [sys.executable, "-m", "neuralcleave.mcp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logger.info("mcp.spawn pid=%d", self._proc.pid)
        return self._proc.pid

    def kill(self) -> bool:
        """Terminate the subprocess.  Returns True if a process was killed."""
        if self._proc is None or self._proc.poll() is not None:
            self._proc = None
            return False
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        logger.info("mcp.kill pid=%d", self._proc.pid)
        self._proc = None
        return True

    def status(self) -> dict[str, object]:
        """Return a status dict suitable for the gateway API."""
        pid = self.pid
        return {
            "running": pid is not None,
            "pid": pid,
        }


# Module-level singleton used by the gateway routes
MCP_PROCESS: McpServerProcess = McpServerProcess()


async def spawn_async() -> int:
    """Async wrapper: spawn the MCP subprocess in a thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, MCP_PROCESS.spawn)


async def kill_async() -> bool:
    """Async wrapper: terminate the MCP subprocess in a thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, MCP_PROCESS.kill)
