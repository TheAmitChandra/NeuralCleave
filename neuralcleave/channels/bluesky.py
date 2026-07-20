"""Bluesky channel adapter — AT Protocol (atproto).

Polls Bluesky notifications for @-mentions using the AT Protocol XRPC API.
Uses only ``aiohttp`` (already a gateway dependency) — no extra SDK needed.

Authentication uses Bluesky **app passwords** (Settings → App Passwords), NOT
your main account password, to limit blast radius if the token leaks.

Inbound:
    Polls ``app.bsky.notification.listNotifications`` every
    ``poll_interval`` seconds (default 30). Processes notifications of type
    ``"mention"`` by default; override with ``notify_types``.

Outbound:
    ``send(target, text)`` creates a post that @-mentions *target* (handle or
    DID). If ``reply_to`` is a post URI (``at://...``), the post is threaded
    as a reply. Sends to the configured PDS (default ``bsky.social``).

Config keys::

    channels.bluesky.handle         = "mybothandle.bsky.social"
    channels.bluesky.password       = "ENV:BSKY_APP_PASSWORD"
    channels.bluesky.pds_url        = "https://bsky.social"         # optional
    channels.bluesky.poll_interval  = 30                             # optional
    channels.bluesky.notify_types   = ["mention"]                    # optional
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_DEFAULT_PDS = "https://bsky.social"
_DEFAULT_POLL = 30.0
_SESSION_ENDPOINT = "/xrpc/com.atproto.server.createSession"
_REFRESH_ENDPOINT = "/xrpc/com.atproto.server.refreshSession"
_NOTIF_LIST = "/xrpc/app.bsky.notification.listNotifications"
_NOTIF_SEEN = "/xrpc/app.bsky.notification.updateSeen"
_CREATE_RECORD = "/xrpc/com.atproto.repo.createRecord"
_DESCRIBE = "/xrpc/com.atproto.server.describeServer"


class BlueskyAdapter(ChannelAdapter):
    """Bluesky adapter — polls AT Protocol notifications, posts replies.

    Requires:
        pip install aiohttp  (already installed with the gateway)

    The adapter token-refreshes automatically when the session expires.
    All posts use the ``app.bsky.feed.post`` lexicon.
    """

    channel_id = "bluesky"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._handle = str(config.get("handle", ""))
        self._password = self._resolve(config.get("password", ""))
        self._pds_url = str(config.get("pds_url", _DEFAULT_PDS)).rstrip("/")
        self._poll_interval = float(config.get("poll_interval", _DEFAULT_POLL))
        self._notify_types: list[str] = list(config.get("notify_types", ["mention"]))

        self._access_jwt: str = ""
        self._refresh_jwt: str = ""
        self._did: str = ""               # our bot's DID
        self._last_seen_at: str = ""      # ISO-8601; marks notifications as read up to here
        self._poll_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._session: Any | None = None  # aiohttp.ClientSession

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            import aiohttp  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install aiohttp")

        if not self._handle or not self._password:
            raise RuntimeError("BlueskyAdapter requires 'handle' and 'password' in config")

        self._session = aiohttp.ClientSession()
        await self._authenticate()
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("bluesky.connected handle=%s did=%s", self._handle, self._did)

    async def disconnect(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self._session:
            await self._session.close()
            self._session = None
        self._access_jwt = ""
        self._refresh_jwt = ""
        logger.info("bluesky.disconnected handle=%s", self._handle)

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Post a Bluesky message that @-mentions *target*.

        Args:
            target:   Handle or DID to @-mention (e.g. ``user.bsky.social``).
            text:     Post text. Mention of *target* is prepended if not included.
            reply_to: ``at://`` URI of the post to reply to. When set, the
                      reply ``root`` is also set so the thread displays correctly.
        """
        if not self._session or not self._access_jwt:
            return None

        mention = f"@{target}" if not target.startswith("@") else target
        content = f"{mention} {text}" if mention not in text else text
        # Bluesky character limit is 300 graphemes; truncate safely
        content = content[:300]

        record: dict[str, Any] = {
            "$type": "app.bsky.feed.post",
            "text": content,
            "createdAt": _utc_now(),
        }

        if reply_to and reply_to.startswith("at://"):
            # For a threaded reply, both reply.root and reply.parent are required.
            # When we only have the direct parent URI, root == parent is acceptable.
            record["reply"] = {
                "root": {"uri": reply_to, "cid": ""},
                "parent": {"uri": reply_to, "cid": ""},
            }

        body = {
            "repo": self._did,
            "collection": "app.bsky.feed.post",
            "record": record,
        }

        try:
            resp_data = await self._post(_CREATE_RECORD, body)
            uri = resp_data.get("uri", "")
            logger.debug("bluesky.sent target=%s uri=%s", target, uri)
            return uri
        except Exception as exc:
            logger.error("bluesky.send failed target=%s: %s", target, exc)
            return None

    async def ping(self) -> bool:
        """Return True if the PDS is reachable and we have a valid session."""
        if not self._session or not self._access_jwt:
            return False
        try:
            await self._get(_DESCRIBE)
            return True
        except Exception:
            return False

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["handle", "password"],
            "properties": {
                "handle": {"type": "string", "description": "Bluesky handle (e.g. mybot.bsky.social)."},
                "password": {"type": "string", "description": "App password (ENV:BSKY_APP_PASSWORD)."},
                "pds_url": {"type": "string", "default": _DEFAULT_PDS, "description": "AT Protocol PDS URL."},
                "poll_interval": {"type": "number", "default": _DEFAULT_POLL, "description": "Seconds between notification polls."},
                "notify_types": {"type": "array", "items": {"type": "string"}, "default": ["mention"],
                                 "description": "Notification types to process (mention, reply, like, repost, follow)."},
            },
        }

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _authenticate(self) -> None:
        data = await self._post(
            _SESSION_ENDPOINT,
            {"identifier": self._handle, "password": self._password},
            authed=False,
        )
        self._access_jwt = data["accessJwt"]
        self._refresh_jwt = data.get("refreshJwt", "")
        self._did = data.get("did", "")

    async def _refresh_token(self) -> None:
        if not self._refresh_jwt or not self._session:
            await self._authenticate()
            return
        try:
            data = await self._post(_REFRESH_ENDPOINT, {}, token=self._refresh_jwt)
            self._access_jwt = data["accessJwt"]
            self._refresh_jwt = data.get("refreshJwt", self._refresh_jwt)
        except Exception:
            await self._authenticate()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_notifications()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("bluesky.poll error: %s", exc)
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def _poll_notifications(self) -> None:
        params: dict[str, Any] = {"limit": 20}
        if self._last_seen_at:
            # The API doesn't support `since`, but we filter locally below
            pass

        try:
            data = await self._get(_NOTIF_LIST, params=params)
        except Exception as exc:
            logger.warning("bluesky.list_notifications error: %s", exc)
            return

        notifications = data.get("notifications", [])
        new_seen_at = data.get("seenAt") or _utc_now()
        processed_any = False

        for notif in notifications:
            # Skip already-seen notifications (indexedAt <= last_seen_at)
            indexed_at = notif.get("indexedAt", "")
            if self._last_seen_at and indexed_at <= self._last_seen_at:
                continue
            if notif.get("isRead", False):
                continue

            notif_type = notif.get("reason", "")
            if notif_type not in self._notify_types:
                continue

            author = notif.get("author", {})
            author_did = author.get("did", "")

            # Echo guard: skip our own notifications
            if author_did and author_did == self._did:
                continue

            msg = self._build_inbound(notif, author)
            if msg:
                await self._dispatch(msg)
                processed_any = True

        if processed_any or not self._last_seen_at:
            self._last_seen_at = new_seen_at
            await self._mark_seen(new_seen_at)

    def _build_inbound(self, notif: dict[str, Any], author: dict[str, Any]) -> InboundMessage | None:
        record = notif.get("record", {})
        text = record.get("text", "").strip()
        if not text:
            return None

        author_handle = author.get("handle", author.get("did", "unknown"))
        author_name = author.get("displayName") or author_handle
        uri = notif.get("uri", "")

        # Collect image/embed attachments
        attachments: list[Attachment] = []
        embed = record.get("embed") or {}
        if embed.get("$type") == "app.bsky.embed.images":
            for img in embed.get("images", []):
                alt = img.get("alt", "")
                attachments.append(Attachment(type="image", filename=alt or "image"))

        return InboundMessage(
            channel=self.channel_id,
            sender_id=author.get("did", author_handle),
            sender_name=author_name,
            text=text,
            attachments=attachments,
            thread_id=uri,
            reply_to_id=record.get("reply", {}).get("parent", {}).get("uri"),
            raw=notif,
        )

    async def _mark_seen(self, seen_at: str) -> None:
        try:
            await self._post(_NOTIF_SEEN, {"seenAt": seen_at})
        except Exception as exc:
            logger.debug("bluesky.mark_seen error: %s", exc)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get(
        self, endpoint: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._access_jwt}"}
        url = f"{self._pds_url}{endpoint}"
        async with self._session.get(url, params=params, headers=headers) as resp:
            if resp.status == 401:
                await self._refresh_token()
                headers["Authorization"] = f"Bearer {self._access_jwt}"
                async with self._session.get(url, params=params, headers=headers) as r2:
                    r2.raise_for_status()
                    return await r2.json()
            resp.raise_for_status()
            return await resp.json()

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any],
        *,
        authed: bool = True,
        token: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if authed or token:
            headers["Authorization"] = f"Bearer {token or self._access_jwt}"
        url = f"{self._pds_url}{endpoint}"
        async with self._session.post(url, json=body, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""


def _utc_now() -> str:
    """Return current UTC time as ISO-8601 string with Z suffix."""
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
