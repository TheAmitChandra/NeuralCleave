"""Microsoft Teams channel adapter — Azure Bot Framework webhook receiver.

CortexFlow acts as a Bot Framework bot. Microsoft Teams sends Activity JSON
(type="message") via HTTPS POST to this adapter's webhook endpoint.
The adapter parses the activity, fires the registered message handler,
and replies via the Bot Connector REST API.

Config keys:
    app_id          Bot Framework App ID (ENV:TEAMS_APP_ID)
    app_password    Bot Framework App Password (ENV:TEAMS_APP_PASSWORD)
    webhook_port    Local port for the aiohttp server (default: 7435)
    path            Webhook URL path (default: /teams/messages)

Outbound send:
    target = "<service_url>|<conversation_id>"
    The adapter calls POST {service_url}/v3/conversations/{conv_id}/activities
    with a Bearer token obtained from the Bot Framework token endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from cortexflow_ai.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
_BOT_SCOPE = "https://api.botframework.com/.default"


class TeamsAdapter(ChannelAdapter):
    """Microsoft Teams adapter via the Azure Bot Framework Activity protocol."""

    channel_id = "teams"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._app_id: str = self._resolve(config.get("app_id", ""))
        self._app_password: str = self._resolve(config.get("app_password", ""))
        self._webhook_port: int = int(config.get("webhook_port", 7435))
        self._path: str = config.get("path", "/teams/messages")
        self._runner: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server."""
        from aiohttp import web

        app = web.Application()
        app.router.add_post(self._path, self._handle_activity)
        app.router.add_get(self._path, self._health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._webhook_port)
        await site.start()
        logger.info(
            "teams.connected port=%d path=%s", self._webhook_port, self._path
        )

    async def disconnect(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

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
        """Send a reply to a Teams conversation.

        *target* must be formatted as "<service_url>|<conversation_id>".
        Returns the Bot Connector activity ID on success, None on error.
        """
        if "|" not in target:
            logger.warning("teams.send invalid target format: %s", target)
            return None

        service_url, conv_id = target.split("|", 1)
        token = await self._get_token()
        if not token:
            return None

        try:
            import httpx

            url = f"{service_url.rstrip('/')}/v3/conversations/{conv_id}/activities"
            payload: dict[str, Any] = {
                "type": "message",
                "text": text,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                return resp.json().get("id")
        except Exception as exc:
            logger.error("teams.send failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Inbound handler
    # ------------------------------------------------------------------

    async def _handle_activity(self, request: Any) -> Any:
        from aiohttp import web

        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        activity_type = body.get("type", "")
        if activity_type != "message":
            return web.Response(status=200, text="OK")

        text = (body.get("text") or "").strip()
        if not text:
            return web.Response(status=200, text="OK")

        sender = body.get("from") or {}
        service_url = body.get("serviceUrl", "")
        conv_id = (body.get("conversation") or {}).get("id", "")

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=sender.get("id", "unknown"),
            sender_name=sender.get("name", ""),
            text=text,
            thread_id=f"{service_url}|{conv_id}" if service_url and conv_id else conv_id,
            timestamp=time.time(),
            raw=body,
        )

        asyncio.create_task(self._dispatch(msg))
        return web.Response(status=200, text="OK")

    async def _health(self, request: Any) -> Any:
        from aiohttp import web

        return web.Response(status=200, text="Teams adapter OK")

    # ------------------------------------------------------------------
    # Token acquisition (Bot Framework OAuth2)
    # ------------------------------------------------------------------

    async def _get_token(self) -> str | None:
        if not self._app_id or not self._app_password:
            return None
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._app_id,
                        "client_secret": self._app_password,
                        "scope": _BOT_SCOPE,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                return resp.json().get("access_token")
        except Exception as exc:
            logger.error("teams.token_error: %s", exc)
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
            "required": ["app_id", "app_password"],
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "Azure Bot Framework App ID (ENV:TEAMS_APP_ID)",
                },
                "app_password": {
                    "type": "string",
                    "description": "App Password (ENV:TEAMS_APP_PASSWORD)",
                },
                "webhook_port": {"type": "integer", "default": 7435},
                "path": {"type": "string", "default": "/teams/messages"},
            },
        }
