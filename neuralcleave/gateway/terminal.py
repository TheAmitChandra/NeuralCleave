"""WebSocket terminal endpoint — runs shell commands and streams output.

Protocol (JSON over WebSocket):
  Client → {"type": "run",       "cmd": "neuralcleave status"}
  Client → {"type": "interrupt"}
  Server → {"type": "ready",     "shell": "/bin/bash"}
  Server → {"type": "output",    "data": "...", "stream": "stdout|stderr"}
  Server → {"type": "exit",      "code": 0}
  Server → {"type": "error",     "message": "..."}

Security: the endpoint only accepts connections from the local gateway
(127.0.0.1 / localhost / Tauri virtual host) — enforced at the CORS
middleware level in main.py. Commands run with the same OS user that
started the gateway, which is expected for a personal-use desktop tool.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Bytes read per chunk from subprocess stdout/stderr
_CHUNK = 4096
# Hard timeout per command (seconds) — prevents runaway processes
_TIMEOUT = 120


def _default_shell() -> list[str]:
    if sys.platform == "win32":
        return ["cmd.exe"]
    return [os.environ.get("SHELL", "/bin/bash")]


async def _send(websocket: WebSocket, msg: dict[str, Any]) -> None:
    try:
        await websocket.send_text(json.dumps(msg))
    except Exception:
        pass


@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket) -> None:
    """Embedded terminal WebSocket — one command at a time."""
    await websocket.accept()

    shell = _default_shell()
    await _send(websocket, {"type": "ready", "shell": shell[0]})

    current_proc: asyncio.subprocess.Process | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "interrupt":
                if current_proc and current_proc.returncode is None:
                    try:
                        current_proc.terminate()
                    except Exception:
                        pass
                continue

            if msg_type != "run":
                await _send(
                    websocket,
                    {"type": "error", "message": f"Unknown message type: {msg_type!r}"},
                )
                continue

            cmd = (msg.get("cmd") or "").strip()
            if not cmd:
                await _send(websocket, {"type": "ready", "shell": shell[0]})
                continue

            await _run_command(websocket, cmd)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("terminal ws error: %s", exc)
    finally:
        if current_proc and current_proc.returncode is None:
            try:
                current_proc.terminate()
            except Exception:
                pass


async def _run_command(websocket: WebSocket, cmd: str) -> None:
    """Execute *cmd* in a subprocess and stream output back over *websocket*."""
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ},
        )

        async def _stream(reader: asyncio.StreamReader, stream: str) -> None:
            while True:
                chunk = await reader.read(_CHUNK)
                if not chunk:
                    break
                await _send(
                    websocket,
                    {
                        "type": "output",
                        "data": chunk.decode("utf-8", errors="replace"),
                        "stream": stream,
                    },
                )

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    _stream(proc.stdout, "stdout"),  # type: ignore[arg-type]
                    _stream(proc.stderr, "stderr"),  # type: ignore[arg-type]
                ),
                timeout=_TIMEOUT,
            )
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.terminate()
            await _send(
                websocket,
                {
                    "type": "output",
                    "data": "\r\n\x1b[33m[Command timed out after 120 s]\x1b[0m\r\n",
                    "stream": "stderr",
                },
            )

        await proc.wait()
        await _send(websocket, {"type": "exit", "code": proc.returncode or 0})

    except Exception as exc:
        logger.error("terminal command error: %s", exc)
        await _send(
            websocket,
            {"type": "output", "data": f"\r\nError: {exc}\r\n", "stream": "stderr"},
        )
        await _send(websocket, {"type": "exit", "code": 1})
    finally:
        await _send(websocket, {"type": "ready", "shell": _default_shell()[0]})
