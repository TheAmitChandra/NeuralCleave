"""Signal channel adapter — wraps the signal-cli Java CLI tool.

signal-cli (https://github.com/AsamK/signal-cli) is an open-source CLI for
Signal. This adapter runs it as a subprocess and parses JSON output.

Setup:
    1. Download signal-cli from https://github.com/AsamK/signal-cli/releases
    2. Register or link a device: signal-cli link -n "CortexFlow"
    3. Set SIGNAL_CLI_PATH env var or specify in config

    config:
        channels.signal.phone_number = "+14155551234"  # your registered number
        channels.signal.cli_path     = "ENV:SIGNAL_CLI_PATH"  # path to signal-cli binary
        channels.signal.data_path    = "~/.local/share/signal-cli"  # optional

Usage::

    adapter = SignalAdapter({
        "phone_number": "+14155551234",
        "cli_path": "/usr/local/bin/signal-cli",
    })
    adapter.on_message(my_handler)
    await adapter.connect()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_RECEIVE_INTERVAL = 5.0  # seconds between polling cycles (JSON-RPC mode)


class SignalAdapter(ChannelAdapter):
    """Signal messenger adapter via signal-cli subprocess.

    Uses signal-cli's JSON-RPC daemon mode (``signal-cli -o json daemon``)
    for efficient message streaming without polling.
    """

    channel_id = "signal"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._phone = str(config.get("phone_number", ""))
        self._cli_path = self._resolve(config.get("cli_path", "signal-cli"))
        self._data_path = str(config.get("data_path", ""))
        self._process: asyncio.subprocess.Process | None = None  # type: ignore[name-defined]
        self._read_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        cli = self._cli_path or "signal-cli"
        cmd: list[str] = [cli]
        if self._data_path:
            cmd += ["--data-path", os.path.expanduser(self._data_path)]
        if self._phone:
            cmd += ["-a", self._phone]
        cmd += ["-o", "json", "daemon", "--no-receive-on-start"]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"signal-cli not found at {cli!r}. "
                "Download from https://github.com/AsamK/signal-cli/releases"
            )

        self._read_task = asyncio.create_task(self._read_loop())
        logger.info("signal.connected phone=%s cli=%s", self._phone, cli)

    async def disconnect(self) -> None:
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        logger.info("signal.disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list | None = None,
    ) -> str | None:
        """Send a Signal message to *target* (phone number or group ID)."""
        if not self._process or not self._process.stdin:
            return None

        rpc_id = f"send-{id(text)}"
        # Use JSON-RPC to send
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": "send",
            "params": {"recipient": [target], "message": text},
            "id": rpc_id,
        }
        try:
            data = (json.dumps(request) + "\n").encode()
            self._process.stdin.write(data)
            await self._process.stdin.drain()
            logger.debug("signal.sent to=%s len=%d", target, len(text))
            return rpc_id
        except Exception as exc:
            logger.error("signal.send failed to=%s: %s", target, exc)
            return None

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["phone_number"],
            "properties": {
                "phone_number": {"type": "string", "description": "Your registered Signal phone number."},
                "cli_path": {"type": "string", "default": "signal-cli", "description": "Path to signal-cli binary (ENV:SIGNAL_CLI_PATH)."},
                "data_path": {"type": "string", "description": "signal-cli data directory (default: ~/.local/share/signal-cli)."},
            },
        }

    # ------------------------------------------------------------------
    # JSON-RPC reader
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        if not self._process or not self._process.stdout:
            return
        try:
            async for raw_line in self._process.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    await self._process_event(payload)
                except json.JSONDecodeError:
                    logger.debug("signal.non_json line=%s", line[:80])
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("signal.read_loop error: %s", exc)

    async def _process_event(self, payload: dict) -> None:
        """Parse a JSON-RPC notification from signal-cli daemon."""
        # signal-cli daemon emits "receive" method notifications
        method = payload.get("method", "")
        if method != "receive":
            return

        params = payload.get("params", {})
        envelope = params.get("envelope", {})
        data_msg = envelope.get("dataMessage", {})
        text = str(data_msg.get("message", "")).strip()
        if not text:
            return

        source = envelope.get("source", envelope.get("sourceNumber", "unknown"))
        source_name = envelope.get("sourceName", source)
        group_info = data_msg.get("groupInfo", {})
        thread_id = group_info.get("groupId") if group_info else None

        # Collect attachments
        attachments: list[Attachment] = []
        for att in data_msg.get("attachments", []):
            attachments.append(
                Attachment(
                    type="document",
                    filename=att.get("filename"),
                    mime_type=att.get("contentType"),
                )
            )

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=source,
            sender_name=source_name,
            text=text,
            attachments=attachments,
            thread_id=thread_id,
            raw=envelope,
        )

        if self._handler:
            asyncio.create_task(self._handler(msg))

        logger.debug("signal.received from=%s len=%d", source, len(text))

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            return os.getenv(value[4:], "")
        return value or ""
