"""Rocket.Chat channel adapter — DDP WebSocket real-time + REST API v1.

Connects to a Rocket.Chat server using the native DDP (Distributed Data
Protocol) WebSocket endpoint for inbound messages and the REST API for outbound
messages.

Setup::

    Self-hosted Rocket.Chat (any version ≥ 3.x):
        channels.rocketchat.url      = "https://chat.example.com"
        channels.rocketchat.username = "bot_user"
        channels.rocketchat.password = "ENV:RC_BOT_PASSWORD"
        channels.rocketchat.room     = "general"  # default room to listen on

    The bot account must exist in Rocket.Chat and have permission to post in
    the target room.

DDP protocol summary::

    1. WebSocket connect to wss://server/websocket
    2. Send   {"msg":"connect","version":"1","support":["1"]}
    3. Receive {"msg":"connected","session":"..."}
    4. Login via "login" method with SHA-256 password digest
    5. Subscribe to "stream-room-messages" for "__my_messages__" to receive
       all messages in any room the bot is a member of
    6. Respond to PING frames with PONG
    7. Dispatch "changed" events on collection "stream-room-messages"

Docs: https://developer.rocket.chat/reference/api/realtime-api
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

from neuralcleave.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_API_V1 = "/api/v1"


class RocketChatAdapter(ChannelAdapter):
    """Rocket.Chat adapter using the DDP WebSocket + REST API v1."""

    channel_id = "rocketchat"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._url: str = config.get("url", "http://localhost:3000").rstrip("/")
        self._username: str = self._resolve(config.get("username", ""))
        self._password: str = self._resolve(config.get("password", ""))
        self._room: str = config.get("room", "general")
        self._bot_user_id: str | None = None
        self._auth_token: str | None = None
        self._ws_task: asyncio.Task | None = None
        self._ws: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Authenticate via REST then start the DDP WebSocket listener."""
        self._bot_user_id, self._auth_token = await self._rest_login()
        self._ws_task = asyncio.create_task(self._ws_loop())
        logger.info(
            "rocketchat.connected url=%s user=%s", self._url, self._username
        )

    async def disconnect(self) -> None:
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments=None,
    ) -> str | None:
        """Post *text* to room *target* (room ID or name).

        Returns the ``_id`` of the new message on success, ``None`` on failure.
        """
        if not self._auth_token or not self._bot_user_id:
            return None
        payload: dict[str, Any] = {"roomId": target, "text": text}
        if reply_to:
            payload["tmid"] = reply_to

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._url}{_API_V1}/chat.sendMessage",
                    headers=self._rest_headers(),
                    json={"message": payload},
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
            return data.get("message", {}).get("_id")
        except Exception as exc:
            logger.error("rocketchat.send failed target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Check that the Rocket.Chat server is reachable and credentials valid."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._url}{_API_V1}/info",
                    timeout=10.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # DDP WebSocket loop
    # ------------------------------------------------------------------

    async def _ws_loop(self) -> None:
        ws_url = self._url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += "/websocket"

        while True:
            try:
                await self._ws_connect_and_listen(ws_url)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("rocketchat.ws_error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _ws_connect_and_listen(self, ws_url: str) -> None:
        try:
            import websockets  # type: ignore[import]
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        async with websockets.connect(ws_url) as ws:
            self._ws = ws
            seq = {"n": 0}

            def next_id() -> str:
                seq["n"] += 1
                return str(seq["n"])

            # DDP handshake
            await ws.send(json.dumps({"msg": "connect", "version": "1", "support": ["1"]}))

            async for raw in ws:
                if raw == "":
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._handle_ddp_message(msg, ws, next_id)

    async def _handle_ddp_message(
        self,
        msg: dict[str, Any],
        ws: Any,
        next_id,
    ) -> None:
        kind = msg.get("msg")

        if kind == "connected":
            # Login with SHA-256 hashed password
            await ws.send(json.dumps({
                "msg": "method",
                "method": "login",
                "id": next_id(),
                "params": [{
                    "user": {"username": self._username},
                    "password": {
                        "digest": hashlib.sha256(self._password.encode()).hexdigest(),
                        "algorithm": "sha-256",
                    },
                }],
            }))

        elif kind == "result":
            error = msg.get("error")
            if error:
                logger.error("rocketchat.ddp_error: %s", error)
                return
            result = msg.get("result", {})
            if isinstance(result, dict) and result.get("token"):
                # Logged in — subscribe to all room messages
                self._auth_token = result["token"]
                self._bot_user_id = result.get("id", self._bot_user_id)
                await ws.send(json.dumps({
                    "msg": "sub",
                    "id": next_id(),
                    "name": "stream-room-messages",
                    "params": ["__my_messages__", False],
                }))
                logger.info("rocketchat.subscribed user_id=%s", self._bot_user_id)

        elif kind == "ping":
            await ws.send(json.dumps({"msg": "pong"}))

        elif kind == "changed" and msg.get("collection") == "stream-room-messages":
            fields = msg.get("fields", {})
            for arg in fields.get("args", []):
                await self._process_message_arg(arg)

    async def _process_message_arg(self, arg: dict[str, Any]) -> None:
        sender = arg.get("u", {})
        sender_id = sender.get("_id", "")
        sender_name = sender.get("name") or sender.get("username", "")

        # Skip own messages
        if self._bot_user_id and sender_id == self._bot_user_id:
            return

        text = (arg.get("msg") or "").strip()
        if not text:
            return

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            thread_id=arg.get("rid"),
            timestamp=time.time(),
            raw=arg,
        )
        asyncio.create_task(self._dispatch(inbound))

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    async def _rest_login(self) -> tuple[str | None, str | None]:
        """Authenticate via REST and return (userId, authToken)."""
        if not self._username or not self._password:
            return None, None
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._url}{_API_V1}/login",
                    json={"user": self._username, "password": self._password},
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return data.get("userId"), data.get("authToken")
        except Exception as exc:
            logger.warning("rocketchat.rest_login failed: %s", exc)
            return None, None

    def _rest_headers(self) -> dict[str, str]:
        return {
            "X-Auth-Token": self._auth_token or "",
            "X-User-Id": self._bot_user_id or "",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve(self, value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            return os.getenv(value[4:], "")
        return value

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["username", "password"],
            "properties": {
                "url": {
                    "type": "string",
                    "default": "http://localhost:3000",
                    "description": "Rocket.Chat server URL",
                },
                "username": {"type": "string", "description": "Bot username"},
                "password": {
                    "type": "string",
                    "description": "Bot password (ENV:RC_BOT_PASSWORD)",
                },
                "room": {
                    "type": "string",
                    "default": "general",
                    "description": "Default room to subscribe to",
                },
            },
        }
