"""Mattermost channel adapter — WebSocket real-time events + REST API.

Connects to a Mattermost server using a personal access token or bot token.
Inbound messages arrive via the Mattermost WebSocket API (``ws(s)://host/api/v4/websocket``).
Outbound messages use the ``POST /api/v4/posts`` REST endpoint.

Config keys:
    url         Base URL of the Mattermost server (default: http://localhost:8065)
    token       Personal access token or bot token (ENV:MATTERMOST_TOKEN)
    team        Team name or ID to filter messages (optional)
    channel     Channel name to listen on (default: town-square)

The adapter filters out its own bot messages to prevent echo loops.

WebSocket event format (Mattermost ≥ 5.x):
    {
        "event": "posted",
        "data": {
            "post": "{\"id\":\"...\",\"user_id\":\"...\",\"channel_id\":\"...\",\"message\":\"Hello\"}",
            "sender_name": "@alice",
            "team_id": "..."
        }
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from neuralcleave.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class MattermostAdapter(ChannelAdapter):
    """Mattermost adapter using the native WebSocket + REST v4 API."""

    channel_id = "mattermost"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._url: str = config.get("url", "http://localhost:8065").rstrip("/")
        self._token: str = self._resolve(config.get("token", ""))
        self._team: str = config.get("team", "")
        self._channel_name: str = config.get("channel", "town-square")
        self._bot_user_id: str | None = None
        self._ws_task: asyncio.Task | None = None
        self._ws: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Resolve bot identity, then start the WebSocket listener."""
        self._bot_user_id = await self._fetch_bot_user_id()
        self._ws_task = asyncio.create_task(self._ws_loop())
        logger.info("mattermost.connected url=%s", self._url)

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
        """Post a message to Mattermost channel *target* (channel_id).

        Returns the new post ID on success, None on error.
        """
        if not self._token:
            return None
        try:
            import httpx

            payload: dict[str, Any] = {"channel_id": target, "message": text}
            if reply_to:
                payload["root_id"] = reply_to

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._url}/api/v4/posts",
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=15.0,
                )
                resp.raise_for_status()
                return resp.json().get("id")
        except Exception as exc:
            logger.error("mattermost.send failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # WebSocket event loop
    # ------------------------------------------------------------------

    async def _ws_loop(self) -> None:
        """Connect to the Mattermost WebSocket and dispatch posted events."""
        ws_url = self._url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += "/api/v4/websocket"

        while True:
            try:
                await self._ws_connect_and_listen(ws_url)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("mattermost.ws_error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _ws_connect_and_listen(self, ws_url: str) -> None:
        try:
            import websockets  # type: ignore[import]
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        async with websockets.connect(
            ws_url,
            extra_headers={"Authorization": f"Bearer {self._token}"},
        ) as ws:
            self._ws = ws
            # Authenticate via challenge message
            await ws.send(json.dumps({
                "seq": 1,
                "action": "authentication_challenge",
                "data": {"token": self._token},
            }))
            async for raw in ws:
                event = json.loads(raw)
                await self._process_event(event)

    async def _process_event(self, event: dict[str, Any]) -> None:
        if event.get("event") != "posted":
            return

        data = event.get("data", {})
        post_raw = data.get("post", "{}")
        try:
            post = json.loads(post_raw) if isinstance(post_raw, str) else post_raw
        except json.JSONDecodeError:
            return

        user_id = post.get("user_id", "")
        if self._bot_user_id and user_id == self._bot_user_id:
            return  # skip own messages

        text = (post.get("message") or "").strip()
        if not text:
            return

        sender_name = data.get("sender_name", "")
        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=user_id,
            sender_name=sender_name.lstrip("@"),
            text=text,
            thread_id=post.get("channel_id"),
            timestamp=time.time(),
            raw=post,
        )
        asyncio.create_task(self._dispatch(msg))

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    async def _fetch_bot_user_id(self) -> str | None:
        if not self._token:
            return None
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._url}/api/v4/users/me",
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.json().get("id")
        except Exception as exc:
            logger.warning("mattermost.fetch_user_id failed: %s", exc)
            return None

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
            "required": ["token"],
            "properties": {
                "url": {"type": "string", "default": "http://localhost:8065"},
                "token": {
                    "type": "string",
                    "description": "Personal access token (ENV:MATTERMOST_TOKEN)",
                },
                "team": {"type": "string", "description": "Team name or ID"},
                "channel": {"type": "string", "default": "town-square"},
            },
        }
