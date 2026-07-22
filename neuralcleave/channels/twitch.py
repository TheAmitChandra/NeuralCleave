"""Twitch channel adapter — Twitch Chat via IRC-over-WebSocket.

NeuralCleave connects to Twitch Chat using the Twitch IRC-over-WebSocket
interface (``wss://irc-ws.chat.twitch.tv:443``).  Inbound ``PRIVMSG``
events are normalised into ``InboundMessage`` objects.  Outbound messages
are sent as IRC ``PRIVMSG`` commands over the same persistent connection.

The adapter requests the ``twitch.tv/tags`` and ``twitch.tv/commands``
capabilities so that structured tag metadata (display-name, user-id,
tmi-sent-ts, message id, …) is available on each message.

Authentication:
    A Twitch OAuth2 token with ``chat:read`` (for reading) and
    ``chat:edit`` (for sending) scopes.  Generate one at
    https://twitchapps.com/tmi/ or via the Twitch OAuth2 flow.

Config keys:
    token           OAuth token, with or without the ``oauth:`` prefix
                    (required)
    bot_username    Bot's Twitch login name in lowercase (required to send
                    and to prevent echo-loop)
    channels        List of Twitch channel names to join (without ``#``,
                    e.g. ``["mychannel"]``)
    host            IRC WebSocket host (default: ``"irc-ws.chat.twitch.tv"``)
    port            IRC WebSocket port (default: 443)
    reconnect_delay Seconds between reconnect attempts (default: 5.0)

Outbound target format:
    Channel name, with or without the leading ``#``
    (e.g. ``"mychannel"`` or ``"#mychannel"``).

Example config.toml::

    [channels.twitch]
    enabled      = true
    token        = "ENV:TWITCH_IRC_TOKEN"
    bot_username = "myneuralcleavebot"
    channels     = ["mychannel", "friendchannel"]
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from neuralcleave.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_IRC_HOST = "irc-ws.chat.twitch.tv"
_IRC_PORT = 443
_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
_CAP_REQ = "CAP REQ :twitch.tv/tags twitch.tv/commands\r\n"


class TwitchAdapter(ChannelAdapter):
    """Twitch Chat adapter — IRC-over-WebSocket with tag support."""

    channel_id = "twitch"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        token = config.get("token", "")
        self._token: str = token.removeprefix("oauth:")
        self._bot_username: str = config.get("bot_username", "").lower()
        raw_channels = config.get("channels", [])
        if isinstance(raw_channels, str):
            raw_channels = [raw_channels]
        self._channels: list[str] = [c.lstrip("#").lower() for c in raw_channels]
        self._host: str = config.get("host", _IRC_HOST)
        self._port: int = int(config.get("port", _IRC_PORT))
        self._reconnect_delay: float = float(config.get("reconnect_delay", 5.0))

        self._ws_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._irc_ws: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Twitch IRC-over-WebSocket and start the message loop."""
        self._stop_event = asyncio.Event()
        self._ws_task = asyncio.create_task(self._irc_loop())
        logger.info(
            "twitch.connecting bot=%s channels=%s",
            self._bot_username,
            self._channels,
        )

    async def disconnect(self) -> None:
        """Disconnect from Twitch IRC and stop the background task."""
        if self._stop_event:
            self._stop_event.set()
        if self._irc_ws is not None:
            try:
                await self._irc_ws.close()
            except Exception:
                pass
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except (asyncio.CancelledError, Exception):
                pass
        self._ws_task = None
        self._irc_ws = None
        logger.info("twitch.disconnected")

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Send a chat message to *target* (a Twitch channel name).

        Returns the channel name (with ``#``) on success, ``None`` on error
        or when not connected.
        """
        if not target:
            logger.warning("twitch.send: target is empty")
            return None
        if self._irc_ws is None:
            logger.warning("twitch.send: not connected")
            return None
        channel = "#" + target.lstrip("#").lower()
        try:
            await self._irc_ws.send_str(f"PRIVMSG {channel} :{text}\r\n")
            return channel
        except Exception as exc:
            logger.error("twitch.send_error channel=%s: %s", channel, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the OAuth token is valid.

        Calls ``GET https://id.twitch.tv/oauth2/validate`` with the token.
        """
        if not self._token:
            return False
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _VALIDATE_URL,
                    headers={"Authorization": f"OAuth {self._token}"},
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # IRC connection loop
    # ------------------------------------------------------------------

    async def _irc_loop(self) -> None:
        """Main reconnect loop — connects to Twitch IRC and processes messages."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            while self._stop_event and not self._stop_event.is_set():
                try:
                    url = f"wss://{self._host}:{self._port}"
                    async with session.ws_connect(
                        url,
                        timeout=aiohttp.ClientTimeout(connect=15.0),
                        heartbeat=60.0,
                    ) as ws:
                        self._irc_ws = ws
                        await self._authenticate(ws)
                        logger.info("twitch.irc_connected host=%s", self._host)

                        async for raw in ws:
                            if self._stop_event.is_set():
                                break
                            if raw.type == aiohttp.WSMsgType.TEXT:
                                for line in raw.data.split("\r\n"):
                                    line = line.strip()
                                    if line:
                                        await self._handle_irc_line(line, ws)
                            elif raw.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                break

                        logger.info("twitch.irc_disconnected")
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    logger.warning("twitch.irc_error: %s", exc)
                finally:
                    self._irc_ws = None

                if self._stop_event and not self._stop_event.is_set():
                    await asyncio.sleep(self._reconnect_delay)

    async def _authenticate(self, ws: Any) -> None:
        """Send CAP REQ, PASS, NICK, and JOIN commands."""
        await ws.send_str(_CAP_REQ)
        await ws.send_str(f"PASS oauth:{self._token}\r\n")
        await ws.send_str(f"NICK {self._bot_username}\r\n")
        for channel in self._channels:
            await ws.send_str(f"JOIN #{channel}\r\n")

    # ------------------------------------------------------------------
    # IRC message handling
    # ------------------------------------------------------------------

    async def _handle_irc_line(self, line: str, ws: Any) -> None:
        """Dispatch a single parsed IRC line to the appropriate handler."""
        tags, prefix, command, params, trailing = self._parse_irc_line(line)

        if command == "PING":
            await ws.send_str(f"PONG :{trailing}\r\n")
        elif command == "PRIVMSG":
            await self._process_privmsg(tags, prefix, params, trailing)
        elif command == "NOTICE":
            if "Login authentication failed" in trailing or "Improperly formatted auth" in trailing:
                logger.error("twitch.auth_error: %s", trailing)
        elif command == "RECONNECT":
            logger.info("twitch.server_requested_reconnect")
            try:
                await ws.close()
            except Exception:
                pass

    async def _process_privmsg(
        self,
        tags: dict[str, str],
        prefix: str,
        params: list[str],
        trailing: str,
    ) -> None:
        """Parse a PRIVMSG and dispatch an InboundMessage."""
        text = trailing.strip()
        if not text:
            return

        channel = params[0] if params else ""
        nick = prefix.split("!")[0] if "!" in prefix else prefix

        if self._bot_username and nick.lower() == self._bot_username:
            return

        display_name = tags.get("display-name") or nick
        user_id = tags.get("user-id") or nick
        msg_id = tags.get("id", "")

        try:
            ts = int(tags["tmi-sent-ts"]) / 1000.0
        except (KeyError, ValueError, TypeError):
            ts = time.time()

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=user_id,
            sender_name=display_name,
            text=text,
            thread_id=channel.lstrip("#"),
            timestamp=ts,
            raw={
                "tags": tags,
                "prefix": prefix,
                "channel": channel,
                "text": trailing,
                "id": msg_id,
            },
        )
        asyncio.create_task(self._dispatch(msg))

    # ------------------------------------------------------------------
    # IRC line parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_irc_line(
        line: str,
    ) -> tuple[dict[str, str], str, str, list[str], str]:
        """Parse a raw IRC line into ``(tags, prefix, command, params, trailing)``.

        Handles the IRCv3 message-tags extension used by Twitch.
        """
        tags: dict[str, str] = {}
        prefix = ""

        if not line:
            return tags, prefix, "", [], ""

        # Tags — ``@key=value;key2=value2 ...``
        if line.startswith("@"):
            space = line.index(" ")
            for kv in line[1:space].split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    tags[k] = v
                else:
                    tags[kv] = ""
            line = line[space + 1 :]

        # Prefix — ``:nick!user@host ...``
        if line.startswith(":"):
            space = line.index(" ")
            prefix = line[1:space]
            line = line[space + 1 :]

        # Command + params + trailing
        if " :" in line:
            main, trailing = line.split(" :", 1)
        else:
            main, trailing = line, ""

        parts = main.split()
        command = parts[0].upper() if parts else ""
        params = parts[1:]

        return tags, prefix, command, params, trailing

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["token", "bot_username"],
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Twitch OAuth token (chat:read + chat:edit scope)",
                },
                "bot_username": {
                    "type": "string",
                    "description": "Bot's Twitch login name in lowercase",
                },
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Twitch channel names to join (without #)",
                },
                "host": {
                    "type": "string",
                    "default": "irc-ws.chat.twitch.tv",
                    "description": "IRC WebSocket host",
                },
                "port": {
                    "type": "integer",
                    "default": 443,
                    "description": "IRC WebSocket port",
                },
                "reconnect_delay": {
                    "type": "number",
                    "default": 5.0,
                    "description": "Seconds between reconnect attempts",
                },
            },
        }
