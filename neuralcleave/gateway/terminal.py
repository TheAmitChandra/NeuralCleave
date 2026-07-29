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

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from neuralcleave import __version__

logger = logging.getLogger(__name__)
router = APIRouter()

# Bytes read per chunk from subprocess stdout/stderr
_CHUNK = 4096
# Hard timeout per command (seconds) — prevents runaway processes
_TIMEOUT = 120

# ---------------------------------------------------------------------------
# Internal API dispatch — maps `neuralcleave <args>` tuples to REST calls
# ---------------------------------------------------------------------------

# (args tuple) → (HTTP method, path)
# Paths are relative to /api/v1.  None method = local-only (no HTTP call).
_NC_CMD_MAP: dict[tuple[str, ...], tuple[str, str]] = {
    ("status",):                    ("GET",  "/api/v1/status"),
    ("channels", "list"):           ("GET",  "/api/v1/channels"),
    ("sessions",):                  ("GET",  "/api/v1/sessions"),
    ("memory", "stats"):            ("GET",  "/api/v1/memory/entries"),
    ("memory", "list"):             ("GET",  "/api/v1/memory/entries"),
    ("plugins", "list"):            ("GET",  "/api/v1/plugins"),
    ("plugins", "reload"):          ("POST", "/api/v1/plugins/reload"),
    ("skills", "list"):             ("GET",  "/api/v1/plugins"),
    ("orchestrator", "list"):       ("GET",  "/api/v1/orchestrator/nodes"),
    ("orchestrator", "status"):     ("GET",  "/api/v1/orchestrator/status"),
    ("hub", "list"):                ("GET",  "/api/v1/hub/packages"),
    ("hub", "status"):              ("GET",  "/api/v1/hub/status"),
    ("metrics",):                   ("GET",  "/api/v1/metrics/snapshot"),
}

_NC_HELP = """\
\x1b[1;36mNeuralCleave Gateway CLI\x1b[0m  v{version}

\x1b[1mUsage:\x1b[0m  neuralcleave <command> [subcommand]

\x1b[1mCommands:\x1b[0m
  status                  Gateway health, uptime, session count
  channels list           All registered channel adapters
  sessions                Active WebSocket sessions
  memory stats            Recent long-term memory entries
  memory search <query>   Semantic memory search
  plugins list            Registered plugins and status
  plugins reload          Hot-reload all plugins
  skills list             Alias for plugins list
  orchestrator list       Registered agent nodes
  orchestrator status     Routing statistics
  hub list                Installed hub packages
  hub search <query>      Search hub package registry
  hub status              Hub installer status
  metrics                 Live metrics snapshot
  --version               Print version
  --help                  Show this help

\x1b[2mTip: use the Quick buttons above to run common commands.\x1b[0m
""".format(version=__version__)


def _pretty_json(data: Any) -> str:
    """Return ANSI-coloured JSON for terminal display."""
    raw = json.dumps(data, indent=2, default=str)
    lines = []
    for line in raw.splitlines():
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith('"') and ":" in stripped:
            key, _, rest = stripped.partition(":")
            lines.append(f"{indent}\x1b[36m{key}\x1b[0m:{rest}")
        elif stripped.startswith('"'):
            lines.append(f"{indent}\x1b[32m{stripped}\x1b[0m")
        elif stripped in ("true", "false"):
            lines.append(f"{indent}\x1b[33m{stripped}\x1b[0m")
        elif stripped == "null":
            lines.append(f"{indent}\x1b[2m{stripped}\x1b[0m")
        else:
            lines.append(line)
    return "\r\n".join(lines)


def _gateway_base() -> str:
    """Best-effort base URL for the local gateway."""
    try:
        from neuralcleave.config import load_config
        cfg = load_config()
        return f"http://127.0.0.1:{cfg.gateway.port}"
    except Exception:
        return "http://127.0.0.1:7432"


async def _call_internal(
    websocket: WebSocket,
    method: str,
    path: str,
    params: dict[str, str] | None = None,
) -> None:
    """Call the internal REST API and stream pretty-printed JSON to *websocket*."""
    base = _gateway_base()
    try:
        async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
            resp = await client.request(method, path, params=params or {})
        if resp.headers.get("content-type", "").startswith("application/json"):
            body = _pretty_json(resp.json())
        else:
            body = resp.text
        colour = "\x1b[32m" if resp.status_code < 400 else "\x1b[31m"
        header = f"{colour}HTTP {resp.status_code}\x1b[0m\r\n"
        await _send(websocket, {"type": "output", "data": header + body + "\r\n", "stream": "stdout"})
        code = 0 if resp.status_code < 400 else 1
    except httpx.ConnectError:
        await _send(websocket, {
            "type": "output",
            "data": "\x1b[31mCould not connect to gateway — is it running?\x1b[0m\r\n",
            "stream": "stderr",
        })
        code = 1
    except Exception as exc:
        await _send(websocket, {
            "type": "output",
            "data": f"\x1b[31mError: {exc}\x1b[0m\r\n",
            "stream": "stderr",
        })
        code = 1
    await _send(websocket, {"type": "exit", "code": code})
    await _send(websocket, {"type": "ready", "shell": _default_shell()[0]})


async def _maybe_dispatch_nc(websocket: WebSocket, cmd: str) -> bool:
    """
    Intercept `neuralcleave …` / `nc …` commands and route them to the
    internal REST API instead of the OS shell (where the CLI is not on PATH
    in a PyInstaller desktop bundle).

    Returns True if the command was handled so the caller skips the shell.
    """
    parts = cmd.strip().split()
    if not parts or parts[0] not in ("neuralcleave", "nc"):
        return False

    args = tuple(parts[1:])

    # --help / no args
    if not args or args == ("--help",):
        await _send(websocket, {"type": "output", "data": "\r\n" + _NC_HELP, "stream": "stdout"})
        await _send(websocket, {"type": "exit", "code": 0})
        await _send(websocket, {"type": "ready", "shell": _default_shell()[0]})
        return True

    # --version
    if args == ("--version",):
        await _send(websocket, {
            "type": "output",
            "data": f"\r\nneuralcleave {__version__}\r\n",
            "stream": "stdout",
        })
        await _send(websocket, {"type": "exit", "code": 0})
        await _send(websocket, {"type": "ready", "shell": _default_shell()[0]})
        return True

    # memory search <query>
    if len(args) >= 3 and args[:2] == ("memory", "search"):
        query = " ".join(args[2:])
        await _call_internal(websocket, "GET", "/api/v1/memory/search", {"q": query})
        return True

    # hub search <query>
    if len(args) >= 3 and args[:2] == ("hub", "search"):
        query = " ".join(args[2:])
        await _call_internal(websocket, "GET", "/api/v1/hub/search", {"q": query})
        return True

    # Mapped commands
    route = _NC_CMD_MAP.get(args)
    if route:
        method, path = route
        await _call_internal(websocket, method, path)
        return True

    # Unknown subcommand
    await _send(websocket, {
        "type": "output",
        "data": (
            f"\r\n\x1b[31mUnknown command:\x1b[0m neuralcleave {' '.join(args)}\r\n"
            "Run \x1b[36mneuralcleave --help\x1b[0m for available commands.\r\n"
        ),
        "stream": "stderr",
    })
    await _send(websocket, {"type": "exit", "code": 1})
    await _send(websocket, {"type": "ready", "shell": _default_shell()[0]})
    return True


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------

def _default_shell() -> list[str]:
    if sys.platform == "win32":
        return ["cmd.exe"]
    return [os.environ.get("SHELL", "/bin/bash")]


async def _send(websocket: WebSocket, msg: dict[str, Any]) -> None:
    try:
        await websocket.send_text(json.dumps(msg))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

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

            # Intercept neuralcleave / nc commands — route internally
            if await _maybe_dispatch_nc(websocket, cmd):
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
