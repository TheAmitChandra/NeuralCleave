"""Nextcloud Talk channel adapter — OCS REST API polling.

CortexFlow connects to Nextcloud Talk rooms by long-polling the chat endpoint.
There is no persistent WebSocket in the Nextcloud Talk OCS API; the adapter
uses ``lastKnownMessageId`` to fetch only new messages on each poll cycle.

Config keys:
    url           Nextcloud base URL (e.g. https://cloud.example.com)
    username      Nextcloud username (ENV:NEXTCLOUD_USERNAME)
    password      App password or user password (ENV:NEXTCLOUD_PASSWORD)
    room_token    Talk room token to poll (e.g. "abc123de")
    poll_interval Seconds between poll requests (default: 5)

OCS API endpoints used:
    GET /ocs/v2.php/apps/spreed/api/v1/chat/{token}
        Query params: lookIntoFuture=1, limit=100, lastKnownMessageId=<id>
    POST /ocs/v2.php/apps/spreed/api/v1/chat/{token}
        Body: {"message": "<text>"}

Authentication: HTTP Basic Auth (username + app password).
All requests include ``OCS-APIRequest: true`` and ``Accept: application/json``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from cortexflow.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_OCS_HEADERS = {
    "OCS-APIRequest": "true",
    "Accept": "application/json",
}


class NextcloudAdapter(ChannelAdapter):
    """Nextcloud Talk adapter using the OCS v2 REST API with long-polling."""

    channel_id = "nextcloud"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._url: str = config.get("url", "https://localhost").rstrip("/")
        self._username: str = self._resolve(config.get("username", ""))
        self._password: str = self._resolve(config.get("password", ""))
        self._room_token: str = config.get("room_token", "")
        self._poll_interval: float = float(config.get("poll_interval", 5))
        self._last_message_id: int = 0
        self._own_user_id: str | None = None
        self._poll_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Resolve own user identity, then start the polling loop."""
        self._own_user_id = await self._fetch_own_user_id()
        self._last_message_id = await self._fetch_last_message_id()
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "nextcloud.connected url=%s room=%s", self._url, self._room_token
        )

    async def disconnect(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

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
        """Post *text* to the room given by *target* (room token).

        Returns the new message ID on success, None on error.
        """
        if not target:
            target = self._room_token
        if not target or not self._username or not self._password:
            return None
        try:
            import httpx

            endpoint = (
                f"{self._url}/ocs/v2.php/apps/spreed/api/v1/chat/{target}"
            )
            payload: dict[str, Any] = {"message": text}
            if reply_to:
                payload["replyTo"] = int(reply_to)

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    endpoint,
                    headers=_OCS_HEADERS,
                    json=payload,
                    auth=(self._username, self._password),
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
                msg_id = (
                    data.get("ocs", {})
                    .get("data", {})
                    .get("id")
                )
                return str(msg_id) if msg_id is not None else None
        except Exception as exc:
            logger.error("nextcloud.send failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("nextcloud.poll_error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        if not self._room_token or not self._username or not self._password:
            return
        try:
            import httpx

            endpoint = (
                f"{self._url}/ocs/v2.php/apps/spreed/api/v1/chat"
                f"/{self._room_token}"
            )
            params: dict[str, Any] = {
                "lookIntoFuture": 1,
                "limit": 100,
                "lastKnownMessageId": self._last_message_id,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    endpoint,
                    headers=_OCS_HEADERS,
                    params=params,
                    auth=(self._username, self._password),
                    timeout=30.0,
                )
                if resp.status_code == 304:
                    return  # no new messages
                resp.raise_for_status()
                messages = (
                    resp.json().get("ocs", {}).get("data", [])
                )
                for msg in messages:
                    await self._process_message(msg)
        except Exception as exc:
            logger.debug("nextcloud._poll_once error: %s", exc)
            raise

    async def _process_message(self, msg: dict[str, Any]) -> None:
        msg_id = int(msg.get("id", 0))
        if msg_id > self._last_message_id:
            self._last_message_id = msg_id

        # Only handle regular chat messages from other users
        if msg.get("systemMessage") or msg.get("messageType") == "system":
            return

        actor_id = msg.get("actorId", "")
        if self._own_user_id and actor_id == self._own_user_id:
            return  # skip own messages

        text = (msg.get("message") or "").strip()
        if not text:
            return

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=actor_id,
            sender_name=msg.get("actorDisplayName", ""),
            text=text,
            thread_id=self._room_token,
            timestamp=float(msg.get("timestamp", time.time())),
            raw=msg,
        )
        asyncio.create_task(self._dispatch(inbound))

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------

    async def _fetch_own_user_id(self) -> str | None:
        if not self._username or not self._password:
            return None
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._url}/ocs/v2.php/cloud/user",
                    headers=_OCS_HEADERS,
                    auth=(self._username, self._password),
                    timeout=10.0,
                )
                resp.raise_for_status()
                return (
                    resp.json().get("ocs", {}).get("data", {}).get("id")
                )
        except Exception as exc:
            logger.warning("nextcloud.fetch_user_id failed: %s", exc)
            return None

    async def _fetch_last_message_id(self) -> int:
        """Fetch the most recent message ID to avoid replaying history on start."""
        if not self._room_token or not self._username or not self._password:
            return 0
        try:
            import httpx

            endpoint = (
                f"{self._url}/ocs/v2.php/apps/spreed/api/v1/chat"
                f"/{self._room_token}"
            )
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    endpoint,
                    headers=_OCS_HEADERS,
                    params={"limit": 1, "lookIntoFuture": 0},
                    auth=(self._username, self._password),
                    timeout=10.0,
                )
                resp.raise_for_status()
                messages = (
                    resp.json().get("ocs", {}).get("data", [])
                )
                if messages:
                    return int(messages[-1].get("id", 0))
        except Exception as exc:
            logger.warning("nextcloud.fetch_last_id failed: %s", exc)
        return 0

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
            "required": ["url", "username", "password", "room_token"],
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Nextcloud base URL",
                },
                "username": {
                    "type": "string",
                    "description": "Nextcloud username (ENV:NEXTCLOUD_USERNAME)",
                },
                "password": {
                    "type": "string",
                    "description": "App password (ENV:NEXTCLOUD_PASSWORD)",
                },
                "room_token": {
                    "type": "string",
                    "description": "Talk room token",
                },
                "poll_interval": {
                    "type": "number",
                    "default": 5,
                    "description": "Seconds between polls",
                },
            },
        }
