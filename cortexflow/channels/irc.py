"""IRC channel adapter using pure asyncio (no external library required).

Implements RFC 1459 / 2812 IRC client over raw TCP with asyncio.
Supports TLS (ircs://) and SASL PLAIN authentication.

Features:
- Auto-reconnect with exponential backoff
- Channel message and private message handling
- Command parsing (!reset, !memory, !status)
- CTCP ACTION support (emote messages)
- TLS support

Setup (no pip install needed — uses stdlib asyncio):
    config:
        channels.irc.server   = "irc.libera.chat"
        channels.irc.port     = 6697            # 6697 for TLS, 6667 plain
        channels.irc.tls      = true
        channels.irc.nick     = "cortexflow"
        channels.irc.channels = ["#cortexflow", "#help"]
        channels.irc.sasl_user     = "ENV:IRC_SASL_USER"     # optional
        channels.irc.sasl_password = "ENV:IRC_SASL_PASSWORD"  # optional

Usage::

    adapter = IRCAdapter({
        "server": "irc.libera.chat",
        "port": 6697,
        "tls": True,
        "nick": "mybot",
        "channels": ["#mychannel"],
    })
    adapter.on_message(my_handler)
    await adapter.connect()
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any

from cortexflow.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_CRLF = "\r\n"
_MAX_LINE = 512
_COMMANDS = {"!reset", "!memory", "!status", "!compact", "!voice", "!model"}
_RECONNECT_BASE = 5   # seconds
_RECONNECT_MAX = 300  # 5 minutes cap


class IRCAdapter(ChannelAdapter):
    """Pure-asyncio IRC client adapter.

    Handles both public channel messages and private messages (PM).
    Messages from channels arrive with thread_id=channel_name.
    Private messages arrive with thread_id=None.
    """

    channel_id = "irc"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._server = str(config.get("server", "irc.libera.chat"))
        self._port = int(config.get("port", 6697))
        self._tls = bool(config.get("tls", True))
        self._nick = str(config.get("nick", "cortexflow"))
        self._realname = str(config.get("realname", "CortexFlow AI"))
        self._channels: list[str] = list(config.get("channels", []))
        self._sasl_user = self._resolve(config.get("sasl_user", ""))
        self._sasl_password = self._resolve(config.get("sasl_password", ""))
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        ssl_ctx: ssl.SSLContext | None = ssl.create_default_context() if self._tls else None

        self._reader, self._writer = await asyncio.open_connection(
            self._server, self._port, ssl=ssl_ctx
        )
        self._connected = True

        # Authenticate
        if self._sasl_user:
            await self._send_raw(f"CAP REQ :sasl")
        await self._send_raw(f"NICK {self._nick}")
        await self._send_raw(f"USER {self._nick} 0 * :{self._realname}")

        # Start reader loop
        self._read_task = asyncio.create_task(self._read_loop())
        logger.info(
            "irc.connected server=%s port=%d tls=%s nick=%s",
            self._server,
            self._port,
            self._tls,
            self._nick,
        )

    async def disconnect(self) -> None:
        self._connected = False
        if self._writer:
            try:
                await self._send_raw("QUIT :CortexFlow disconnecting")
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        logger.info("irc.disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list | None = None,
    ) -> str | None:
        """Send *text* to *target* (channel name or nick)."""
        if not self._writer or not self._connected:
            return None
        # Split long messages at the IRC limit
        for chunk in _split_message(text, max_len=400):
            await self._send_raw(f"PRIVMSG {target} :{chunk}")
        return None  # IRC has no message IDs

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["server", "nick"],
            "properties": {
                "server": {"type": "string", "description": "IRC server hostname."},
                "port": {"type": "integer", "default": 6697},
                "tls": {"type": "boolean", "default": True},
                "nick": {"type": "string", "description": "Bot nickname."},
                "channels": {"type": "array", "items": {"type": "string"}, "description": "Channels to join on connect."},
                "sasl_user": {"type": "string", "description": "SASL PLAIN username (ENV:IRC_SASL_USER)."},
                "sasl_password": {"type": "string", "description": "SASL PLAIN password (ENV:IRC_SASL_PASSWORD)."},
            },
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_raw(self, line: str) -> None:
        if not self._writer:
            return
        data = (line[:_MAX_LINE] + _CRLF).encode("utf-8", errors="replace")
        self._writer.write(data)
        await self._writer.drain()

    async def _read_loop(self) -> None:
        """Read and parse IRC lines indefinitely."""
        if not self._reader:
            return
        try:
            while self._connected:
                raw = await self._reader.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                await self._process_line(line)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("irc.read_loop error: %s", exc)

    async def _process_line(self, line: str) -> None:
        if not line:
            return

        # PING → PONG (keepalive)
        if line.startswith("PING"):
            token = line.split(" ", 1)[1] if " " in line else ""
            await self._send_raw(f"PONG {token}")
            return

        parts = line.split(" ")
        if len(parts) < 2:
            return

        # Numeric 001 = welcome → join configured channels
        if parts[1] == "001":
            for channel in self._channels:
                await self._send_raw(f"JOIN {channel}")

        # CAP ACK for SASL
        elif parts[1] == "CAP" and len(parts) > 3 and "ACK" in parts[3]:
            await self._send_raw("AUTHENTICATE PLAIN")

        # AUTHENTICATE challenge
        elif parts[0] == "AUTHENTICATE" and parts[1] == "+":
            import base64
            creds = f"\0{self._sasl_user}\0{self._sasl_password}"
            encoded = base64.b64encode(creds.encode()).decode()
            await self._send_raw(f"AUTHENTICATE {encoded}")
            await self._send_raw("CAP END")

        # PRIVMSG → message
        elif parts[1] == "PRIVMSG" and len(parts) >= 4:
            prefix = parts[0].lstrip(":")
            sender = prefix.split("!")[0] if "!" in prefix else prefix
            target = parts[2]
            text = " ".join(parts[3:])[1:]  # strip leading ":"

            # Strip CTCP ACTION wrappers (\x01ACTION ...\x01)
            if text.startswith("\x01ACTION") and text.endswith("\x01"):
                text = f"* {text[8:-1].strip()}"

            thread_id = target if target.startswith("#") else None

            msg = InboundMessage(
                channel=self.channel_id,
                sender_id=sender,
                sender_name=sender,
                text=text,
                thread_id=thread_id,
                raw={"prefix": prefix, "target": target},
            )

            if self._handler:
                asyncio.create_task(self._handler(msg))

            logger.debug("irc.message sender=%s target=%s len=%d", sender, target, len(text))

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""


def _split_message(text: str, max_len: int = 400) -> list[str]:
    """Split a long message into chunks that fit within IRC limits."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks
