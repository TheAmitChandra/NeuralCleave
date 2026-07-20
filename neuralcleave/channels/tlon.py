"""Tlon/Urbit channel adapter.

Connects NeuralCleave to the Tlon messaging app running on an Urbit ship
via Urbit's Eyre HTTP API.

Architecture
^^^^^^^^^^^^
Tlon (like all Urbit apps) is reached through Eyre, Urbit's HTTP server.
NeuralCleave acts as an Eyre *HTTP client* — it logs in, opens a long-lived
SSE channel for inbound events, and POSTs poke actions for outbound
messages.  No public webhook URL is required.

Connection flow
^^^^^^^^^^^^^^^
1. ``POST /~/login`` → sets ``urbauth-~ship`` session cookie
2. ``PUT /~/channel/{uid}`` → create a named SSE channel
3. ``POST /~/channel/{uid}`` → subscribe to the ``chat`` agent's
   ``/updates`` path
4. ``GET /~/channel/{uid}`` → SSE stream (background task)
5. For each diff: parse ``add-message`` envelopes → dispatch
   ``InboundMessage``; POST ack so Eyre knows the event was received
6. ``POST /~/channel/{uid}`` → poke ``chat`` with ``chat-action-1``
   mark to send outbound messages

Chat path format (Urbit)
^^^^^^^^^^^^^^^^^^^^^^^^
DMs are stored at ``/~{ship}/dm/~{partner}``.
Group channels live at ``/~{host}/~{channel-name}``.

Config keys
^^^^^^^^^^^
``url``         Base URL of the Urbit ship (default ``"http://localhost:8080"``)
``ship``        Your ship name, e.g. ``"~zod"`` or ``"~sampel-palnet"``
                (required)
``password``    Login password set in your ship (required)
``bot_ship``    Ship name to treat as the bot for echo prevention
                (defaults to ``ship``)

Outbound target format
^^^^^^^^^^^^^^^^^^^^^^
``~sampel-palnet``          DM to that ship
``dm:~sampel-palnet``       Alias for DM
``~host/channel-name``      Group channel message
``group:~host/channel``     Alias for group channel
``path:/~raw/urbit/path``   Use an exact Urbit chat path

Example config.toml::

    [channels.tlon]
    enabled  = true
    url      = "http://localhost:8080"
    ship     = "~sampel-palnet"
    password = "ENV:URBIT_PASSWORD"
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from typing import Any

from neuralcleave.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_LOGIN_PATH = "/~/login"
_CHANNEL_BASE = "/~/channel"
_CHAT_APP = "chat"
_CHAT_SUBSCRIBE_PATH = "/updates"
_CHAT_MARK = "chat-action-1"

_SHIP_RE = re.compile(r"^~[a-z-]+$")


def _urbit_uid() -> str:
    """Return a random Eyre channel UID (e.g. ``0v1.a2b3c4d5``)."""
    raw = secrets.token_hex(5)
    return f"0v1.{raw}"


def _urbit_time_ms() -> int:
    """Current Unix time in milliseconds (Urbit `when` field format)."""
    return int(time.time() * 1000)


def _letter_text(letter: dict[str, Any]) -> str:
    """Extract plain text from a chat letter object.

    Handles both the legacy ``{"text": "..."}`` format and the modern
    ``{"story": {"inline": [...]}}`` format used by newer Tlon versions.
    """
    if "text" in letter:
        return str(letter["text"])
    story = letter.get("story", {})
    parts: list[str] = []
    for item in story.get("inline", []):
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(item.get("code", item.get("italics", item.get("bold", ""))))
    return " ".join(p for p in parts if p).strip()


class TlonAdapter(ChannelAdapter):
    """Tlon adapter — Eyre SSE receiver + chat poke sender."""

    channel_id = "tlon"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._url: str = config.get("url", "http://localhost:8080").rstrip("/")
        self._ship: str = config.get("ship", "")
        self._password: str = config.get("password", "")
        self._bot_ship: str = config.get("bot_ship", "") or self._ship

        self._cookie: str = ""
        self._channel_uid: str = ""
        self._action_id: int = 0
        self._session: Any = None   # aiohttp.ClientSession
        self._task: asyncio.Task | None = None  # SSE reader task

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Login, open Eyre channel, subscribe, start SSE reader."""
        import aiohttp

        if not self._ship or not self._password:
            logger.error("tlon.connect: ship and password are required")
            return

        self._session = aiohttp.ClientSession()
        try:
            await self._login()
        except Exception as exc:
            logger.error("tlon.login_error: %s", exc)
            await self._session.close()
            self._session = None
            return

        self._channel_uid = _urbit_uid()
        try:
            await self._create_channel()
            await self._subscribe()
        except Exception as exc:
            logger.error("tlon.subscribe_error: %s", exc)
            await self._session.close()
            self._session = None
            return

        self._task = asyncio.create_task(self._sse_reader())
        logger.info("tlon.connected ship=%s url=%s", self._ship, self._url)

    async def disconnect(self) -> None:
        """Cancel SSE task and close the session."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        logger.info("tlon.disconnected")

    # ------------------------------------------------------------------
    # Eyre channel management
    # ------------------------------------------------------------------

    async def _login(self) -> None:
        """POST /~/login → store auth cookie."""
        url = f"{self._url}{_LOGIN_PATH}"
        async with self._session.post(
            url,
            data={"password": self._password},
            allow_redirects=False,
        ) as resp:
            cookie_name = f"urbauth-{self._ship}"
            cookie_val = resp.cookies.get(cookie_name)
            if cookie_val is not None:
                self._cookie = cookie_val.value if hasattr(cookie_val, "value") else str(cookie_val)
            if not self._cookie:
                text = await resp.text()
                raise ValueError(f"Login failed (status {resp.status}): {text[:200]}")
        logger.debug("tlon.logged_in ship=%s", self._ship)

    async def _create_channel(self) -> None:
        """PUT /~/channel/{uid} → create the SSE channel on the ship."""
        url = f"{self._url}{_CHANNEL_BASE}/{self._channel_uid}"
        headers = self._auth_headers()
        async with self._session.put(url, headers=headers) as resp:
            if resp.status not in (200, 204):
                raise ValueError(f"create_channel failed: {resp.status}")

    async def _subscribe(self) -> None:
        """POST subscribe action to the chat agent's /updates path."""
        actions = [
            {
                "id": self._next_id(),
                "action": "subscribe",
                "ship": self._ship,
                "app": _CHAT_APP,
                "path": _CHAT_SUBSCRIBE_PATH,
            }
        ]
        await self._post_actions(actions)

    async def _post_actions(self, actions: list[dict[str, Any]]) -> None:
        """POST a JSON list of Eyre actions to our SSE channel."""
        url = f"{self._url}{_CHANNEL_BASE}/{self._channel_uid}"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        async with self._session.post(url, data=json.dumps(actions), headers=headers) as resp:
            if resp.status not in (200, 204):
                body = await resp.text()
                raise ValueError(f"post_actions failed ({resp.status}): {body[:200]}")

    async def _ack(self, event_id: int) -> None:
        """ACK an SSE event so Eyre can discard it."""
        try:
            await self._post_actions(
                [{"id": self._next_id(), "action": "ack", "event-id": event_id}]
            )
        except Exception as exc:
            logger.debug("tlon.ack_error: %s", exc)

    # ------------------------------------------------------------------
    # SSE reader (background task)
    # ------------------------------------------------------------------

    async def _sse_reader(self) -> None:
        """Read the SSE stream and dispatch inbound messages."""
        url = f"{self._url}{_CHANNEL_BASE}/{self._channel_uid}"
        headers = {**self._auth_headers(), "Accept": "text/event-stream"}
        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error("tlon.sse_error status=%d", resp.status)
                    return
                await self._parse_sse(resp.content)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("tlon.sse_reader_error: %s", exc)

    async def _parse_sse(self, content: Any) -> None:
        """Parse SSE lines from the aiohttp response content."""
        event_id: int | None = None
        data_buf: list[str] = []

        async for raw_chunk in content:
            chunk = raw_chunk.decode("utf-8", errors="replace")
            for line in chunk.splitlines():
                if line.startswith("id:"):
                    try:
                        event_id = int(line[3:].strip())
                    except ValueError:
                        pass
                elif line.startswith("data:"):
                    data_buf.append(line[5:].strip())
                elif line == "" and data_buf:
                    payload_str = "\n".join(data_buf)
                    data_buf = []
                    try:
                        payload = json.loads(payload_str)
                    except json.JSONDecodeError:
                        event_id = None
                        continue
                    if event_id is not None:
                        asyncio.create_task(self._ack(event_id))
                    await self._handle_sse_event(payload)
                    event_id = None

    async def _handle_sse_event(self, payload: dict[str, Any]) -> None:
        """Process a single parsed SSE event payload."""
        response = payload.get("response")
        if response == "quit":
            logger.warning("tlon.quit_received; resubscribing")
            try:
                await self._subscribe()
            except Exception as exc:
                logger.error("tlon.resubscribe_error: %s", exc)
            return
        if response != "diff":
            return

        data = payload.get("json", {})
        msg = self._parse_chat_update(data)
        if msg is not None:
            asyncio.create_task(self._dispatch(msg))

    def _parse_chat_update(self, data: dict[str, Any]) -> InboundMessage | None:
        """Convert a ``chat-update-1`` diff payload to ``InboundMessage``.

        Handles both ``add-message`` (older) and ``message`` (newer) shapes.
        """
        envelope = None
        path = ""

        if "add-message" in data:
            ev = data["add-message"]
            path = ev.get("path", "")
            envelope = ev.get("envelope", {})
        elif "message" in data:
            ev = data["message"]
            path = ev.get("path", "")
            envelope = ev.get("envelope", {})
        else:
            return None

        if not envelope:
            return None

        author: str = envelope.get("author", "")
        when_ms: int = envelope.get("when", 0)
        letter: dict[str, Any] = envelope.get("letter", {})
        uid: str = envelope.get("uid", "")

        if self._bot_ship and author == self._bot_ship:
            return None

        text = _letter_text(letter)
        if not text:
            return None

        ts = when_ms / 1000.0 if when_ms else time.time()

        return InboundMessage(
            channel=self.channel_id,
            sender_id=author,
            sender_name=author,
            text=text,
            thread_id=path,
            timestamp=ts,
            raw={"path": path, "uid": uid, "envelope": envelope},
        )

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    def _parse_target(self, target: str) -> tuple[str, str]:
        """Return ``(kind, value)`` from a send target.

        Kind is ``"dm"``, ``"group"``, or ``"path"``.
        """
        if target.startswith("dm:"):
            return "dm", target[3:]
        if target.startswith("group:"):
            return "group", target[6:]
        if target.startswith("path:"):
            return "path", target[5:]
        # bare ~ship → DM; bare ~host/name → group
        if "/" in target:
            return "group", target
        return "dm", target

    def _build_path(self, kind: str, value: str) -> str:
        """Convert a parsed target to a Urbit chat path."""
        if kind == "path":
            return value
        if kind == "dm":
            ship = value if value.startswith("~") else f"~{value}"
            return f"/{self._ship}/dm/{ship}"
        # group: ~host/channel-name
        if "/" in value:
            host, name = value.split("/", 1)
            if not host.startswith("~"):
                host = f"~{host}"
            if not name.startswith("~"):
                name = f"~{name}"
            return f"/{host}/{name}"
        return f"/{value}"

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Poke the ``chat`` agent to send *text* to *target*.

        Returns *target* on success, ``None`` on error.
        """
        if not target:
            logger.warning("tlon.send: target is empty")
            return None
        if not self._session:
            logger.error("tlon.send: not connected")
            return None

        kind, value = self._parse_target(target)
        path = self._build_path(kind, value)

        poke: dict[str, Any] = {
            "id": self._next_id(),
            "action": "poke",
            "ship": self._ship,
            "app": _CHAT_APP,
            "mark": _CHAT_MARK,
            "json": {
                "send-message": {
                    "path": path,
                    "envelope": {
                        "uid": _urbit_uid(),
                        "author": self._ship,
                        "when": _urbit_time_ms(),
                        "letter": {"text": text},
                    },
                }
            },
        }

        try:
            await self._post_actions([poke])
            logger.info("tlon.sent target=%s path=%s", target, path)
            return target
        except Exception as exc:
            logger.error("tlon.send_error target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the Urbit ship is reachable and credentials valid."""
        if not self._url or not self._ship or not self._password:
            return False
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._url}{_LOGIN_PATH}",
                    data={"password": self._password},
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    return resp.status in (200, 204, 302, 301)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["ship", "password"],
            "properties": {
                "url": {
                    "type": "string",
                    "default": "http://localhost:8080",
                    "description": "Base URL of the Urbit ship",
                },
                "ship": {
                    "type": "string",
                    "description": "Your ship name (e.g. ~sampel-palnet)",
                },
                "password": {
                    "type": "string",
                    "description": "Urbit login password",
                },
                "bot_ship": {
                    "type": "string",
                    "description": "Ship name to treat as bot (defaults to ship)",
                },
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._action_id += 1
        return self._action_id

    def _auth_headers(self) -> dict[str, str]:
        if self._cookie:
            return {"Cookie": f"urbauth-{self._ship}={self._cookie}"}
        return {}
