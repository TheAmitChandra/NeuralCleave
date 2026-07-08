"""Google Chat channel adapter — Google Chat Bot via HTTP endpoint.

CortexFlow registers as a Google Chat bot (HTTP endpoint type). Google
sends POST events to this adapter's webhook server; the adapter parses
them, fires the registered message handler, and can send replies via the
Google Chat REST API using service account OAuth2 credentials.

Authentication:
    Service account with the Chat API enabled. The service account JSON
    (downloaded from the Google Cloud Console) can be supplied as:
    - A raw JSON string in ``service_account_json``
    - A file path: ``service_account_json = "/path/to/sa.json"``
    - An environment variable: ``service_account_json = "ENV:GOOGLE_CHAT_SA_JSON"``

Config keys:
    service_account_json  Raw SA JSON, file path, or ENV:VAR (required for send)
    webhook_port          Local port for the aiohttp webhook server (default: 7436)
    path                  Webhook URL path (default: /gchat/messages)
    verification_token    Optional string; if set, inbound requests must include
                          a matching ``token`` field in the JSON body.
    bot_name              Optional display name; messages from this sender are skipped
                          to prevent the bot from responding to its own messages.

Outbound target format:
    ``spaces/<SPACE_ID>``                       — send to space (new thread)
    ``spaces/<SPACE_ID>/threads/<THREAD_ID>``   — reply in existing thread

Example config.toml::

    [channels.google_chat]
    enabled = true
    service_account_json = "ENV:GOOGLE_CHAT_SA_JSON"
    webhook_port = 7436
    path = "/gchat/messages"
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CHAT_API_BASE = "https://chat.googleapis.com/v1"
_CHAT_SCOPES = "https://www.googleapis.com/auth/chat.bot"
_JWT_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"


class GoogleChatAdapter(ChannelAdapter):
    """Google Chat adapter — HTTP endpoint bot with service account OAuth2."""

    channel_id = "google_chat"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._sa_json: str = self._resolve_sa(config.get("service_account_json", ""))
        self._webhook_port: int = int(config.get("webhook_port", 7436))
        self._path: str = config.get("path", "/gchat/messages")
        self._verification_token: str = config.get("verification_token", "")
        self._bot_name: str = config.get("bot_name", "")
        self._runner: Any = None
        self._cached_token: str | None = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server to receive Google Chat events."""
        from aiohttp import web

        app = web.Application()
        app.router.add_post(self._path, self._handle_event)
        app.router.add_get(self._path, self._health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._webhook_port)
        await site.start()
        logger.info("google_chat.connected port=%d path=%s", self._webhook_port, self._path)

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
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Send a message to a Google Chat space or thread.

        *target* must be a Google Chat resource name:
        - ``spaces/<SPACE_ID>`` — posts a new thread in the space
        - ``spaces/<SPACE_ID>/threads/<THREAD_ID>`` — replies in a thread

        Returns the sent message name (e.g. ``spaces/AAA/messages/BBB``) on
        success, ``None`` on error.
        """
        if not target.startswith("spaces/"):
            logger.warning("google_chat.send invalid target (must start with 'spaces/'): %s", target)
            return None

        token = await self._get_token()
        if not token:
            return None

        # Determine whether the target is a thread reply or a new space message
        parts = target.split("/")
        if len(parts) >= 4 and parts[2] == "threads":
            # target = "spaces/X/threads/Y" — post into existing thread
            space_name = f"spaces/{parts[1]}"
            thread_name = f"spaces/{parts[1]}/threads/{parts[3]}"
            payload: dict[str, Any] = {
                "text": text,
                "thread": {"name": thread_name},
            }
        else:
            # target = "spaces/X" — new thread
            space_name = target.rstrip("/")
            payload = {"text": text}

        url = f"{_CHAT_API_BASE}/{space_name}/messages"

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15.0,
                )
                resp.raise_for_status()
                return resp.json().get("name")
        except Exception as exc:
            logger.error("google_chat.send failed target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Inbound handler
    # ------------------------------------------------------------------

    async def _handle_event(self, request: Any) -> Any:
        """Handle an incoming Google Chat event."""
        from aiohttp import web

        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        # Optional verification token check
        if self._verification_token:
            if body.get("token") != self._verification_token:
                return web.Response(status=401, text="Unauthorized")

        event_type = body.get("type", "")

        # Only handle MESSAGE events; ignore ADDED_TO_SPACE, REMOVED_FROM_SPACE, etc.
        if event_type != "MESSAGE":
            return web.Response(status=200, text="OK")

        message = body.get("message") or {}
        text = (message.get("text") or message.get("argumentText") or "").strip()
        if not text:
            return web.Response(status=200, text="OK")

        sender = message.get("sender") or {}
        sender_name = sender.get("displayName", "")

        # Skip the bot's own messages to prevent echo loops
        if self._bot_name and sender_name == self._bot_name:
            return web.Response(status=200, text="OK")

        sender_id = sender.get("name", "unknown")
        space = (message.get("space") or body.get("space") or {}).get("name", "")
        thread = (message.get("thread") or {}).get("name", "")

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            thread_id=thread or space,
            timestamp=time.time(),
            raw=body,
        )

        asyncio.create_task(self._dispatch(msg))
        return web.Response(status=200, text="OK")

    async def _health(self, request: Any) -> Any:
        from aiohttp import web

        return web.Response(status=200, text="Google Chat adapter OK")

    # ------------------------------------------------------------------
    # Service account token acquisition
    # ------------------------------------------------------------------

    async def _get_token(self) -> str | None:
        """Obtain a Google OAuth2 access token via service account JWT flow."""
        if not self._sa_json:
            logger.warning("google_chat.token: no service_account_json configured")
            return None

        # Return cached token if it has more than 60 seconds left
        if self._cached_token and time.time() < self._token_expiry - 60:
            return self._cached_token

        try:
            sa = json.loads(self._sa_json)
        except Exception as exc:
            logger.error("google_chat.token: invalid service_account_json: %s", exc)
            return None

        try:
            import httpx
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key_pem: str = sa["private_key"]
            client_email: str = sa["client_email"]

            now = int(time.time())
            header = {"alg": "RS256", "typ": "JWT"}
            claim = {
                "iss": client_email,
                "scope": _CHAT_SCOPES,
                "aud": _GOOGLE_TOKEN_URL,
                "exp": now + 3600,
                "iat": now,
            }

            def _b64url(data: dict) -> str:
                return base64.urlsafe_b64encode(
                    json.dumps(data, separators=(",", ":")).encode()
                ).rstrip(b"=").decode()

            signing_input = f"{_b64url(header)}.{_b64url(claim)}"

            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(), password=None
            )
            signature = private_key.sign(  # type: ignore[union-attr]
                signing_input.encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
            jwt_token = f"{signing_input}.{sig_b64}"

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _GOOGLE_TOKEN_URL,
                    data={
                        "grant_type": _JWT_GRANT_TYPE,
                        "assertion": jwt_token,
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                self._cached_token = data["access_token"]
                self._token_expiry = time.time() + int(data.get("expires_in", 3600))
                logger.debug("google_chat.token refreshed expires_in=%s", data.get("expires_in"))
                return self._cached_token

        except Exception as exc:
            logger.error("google_chat.token_error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_sa(self, value: str) -> str:
        """Resolve service_account_json to raw JSON string.

        Accepts:
        - Raw JSON string (starts with '{')
        - ``ENV:VAR_NAME`` — read the env var (may be JSON string or file path)
        - File path — read and return file contents
        """
        if not value:
            return ""
        if isinstance(value, str) and value.startswith("ENV:"):
            value = os.getenv(value[4:], "")
        if value.startswith("{"):
            return value
        # Treat as file path
        try:
            path = os.path.expanduser(value)
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
        return value

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["service_account_json"],
            "properties": {
                "service_account_json": {
                    "type": "string",
                    "description": "Service account JSON (raw, file path, or ENV:VAR)",
                },
                "webhook_port": {"type": "integer", "default": 7436},
                "path": {"type": "string", "default": "/gchat/messages"},
                "verification_token": {
                    "type": "string",
                    "description": "Optional token to verify inbound request authenticity",
                },
                "bot_name": {
                    "type": "string",
                    "description": "Bot display name; messages from this sender are ignored",
                },
            },
        }
