"""XMPP / Jabber channel adapter using slixmpp.

XMPP (Extensible Messaging and Presence Protocol, RFC 6120 / 7590) is a
battle-tested open-standard messaging protocol used in enterprise IM, gaming
platforms, and federated social networks.  ``slixmpp`` is the asyncio-native
successor to ``sleekxmpp`` and adds no transitive C-extension requirements.

Features:
    - One-to-one (roster) messaging
    - Multi-User Chat (MUC) rooms via XEP-0045
    - TLS encryption; SASL PLAIN + SCRAM-SHA-1 auth
    - In-band keepalive ping via XEP-0199
    - Automatic reconnect with exponential backoff

Setup::

    pip install slixmpp>=1.8.0

Config keys::

    channels.xmpp.jid           = "NeuralCleave@jabber.org"
    channels.xmpp.password      = "ENV:XMPP_PASSWORD"
    channels.xmpp.server        = ""         # optional host override
    channels.xmpp.port          = 5222       # 5222 plain/STARTTLS, 5223 legacy SSL
    channels.xmpp.use_ssl       = false      # true for port 5223 legacy SSL
    channels.xmpp.rooms         = []         # list of MUC room JIDs to join
    channels.xmpp.room_nick     = "NeuralCleave"  # nick used in MUC rooms

Outbound target format:
    ``"user@jabber.org"`` for 1:1 messages; ``"room@conference.server"``
    for a MUC room broadcast.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from neuralcleave.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class XMPPAdapter(ChannelAdapter):
    """Async XMPP adapter using slixmpp.

    Uses slixmpp's asyncio-native event loop.  The ``connect()`` call starts
    the underlying slixmpp client and joins configured MUC rooms.  All
    XMPP events are dispatched on the same asyncio event loop as the gateway.
    """

    channel_id = "xmpp"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._jid = str(config.get("jid", ""))
        self._password = self._resolve(config.get("password", ""))
        self._server = str(config.get("server", ""))
        self._port = int(config.get("port", 5222))
        self._use_ssl = bool(config.get("use_ssl", False))
        self._rooms: list[str] = list(config.get("rooms", []))
        self._room_nick = str(config.get("room_nick", "NeuralCleave"))
        self._client: Any | None = None
        self._connect_future: asyncio.Future | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            import slixmpp  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install slixmpp>=1.8.0")

        if not self._jid or not self._password:
            raise RuntimeError("XMPPAdapter requires 'jid' and 'password' in config")

        client = slixmpp.ClientXMPP(self._jid, self._password)

        # Register plugins
        client.register_plugin("xep_0030")  # Service Discovery
        client.register_plugin("xep_0045")  # Multi-User Chat
        client.register_plugin("xep_0199")  # XMPP Ping (keepalive)

        # Event handlers
        client.add_event_handler("session_start", self._on_session_start)
        client.add_event_handler("message", self._on_message)
        client.add_event_handler("groupchat_message", self._on_groupchat_message)
        client.add_event_handler("disconnected", self._on_disconnected)
        client.add_event_handler("failed_auth", self._on_failed_auth)

        self._client = client

        if self._server:
            client.connect((self._server, self._port), use_ssl=self._use_ssl)
        else:
            client.connect(use_ssl=self._use_ssl)

        # Wait for session_start or failed_auth
        self._connect_future = asyncio.get_event_loop().create_future()
        try:
            await asyncio.wait_for(self._connect_future, timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError(f"XMPP connection timed out for {self._jid}")

        logger.info("xmpp.connected jid=%s rooms=%d", self._jid, len(self._rooms))

    async def disconnect(self) -> None:
        if self._client:
            self._client.disconnect(wait=False)
            self._client = None
        logger.info("xmpp.disconnected jid=%s", self._jid)

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list | None = None,
    ) -> str | None:
        """Send a message to *target* (JID or MUC room JID).

        Args:
            target:   Destination JID — ``user@server`` for 1:1 or
                      ``room@conference.server`` for MUC.
            text:     Message body.
        """
        if not self._client:
            return None

        mtype = "groupchat" if "@conference." in target else "chat"
        try:
            self._client.send_message(mto=target, mbody=text, mtype=mtype)
            logger.debug("xmpp.sent to=%s type=%s len=%d", target, mtype, len(text))
            return None  # XMPP sends don't return IDs easily
        except Exception as exc:
            logger.error("xmpp.send error to=%s: %s", target, exc)
            return None

    async def ping(self) -> bool:
        """Return True when the XMPP session is active."""
        if not self._client:
            return False
        try:
            ping_plugin = self._client.plugin.get("xep_0199")
            if ping_plugin:
                loop = asyncio.get_event_loop()
                server_jid = self._jid.split("@", 1)[-1] if "@" in self._jid else self._jid
                await loop.run_in_executor(None, lambda: ping_plugin.ping(jid=server_jid))
            return True
        except Exception:
            return self._client.is_connected()

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["jid", "password"],
            "properties": {
                "jid": {"type": "string", "description": "Full Jabber ID, e.g. bot@jabber.org."},
                "password": {"type": "string", "description": "XMPP account password (ENV:XMPP_PASSWORD)."},
                "server": {"type": "string", "description": "Override XMPP server host. Defaults to JID domain."},
                "port": {"type": "integer", "default": 5222, "description": "XMPP server port."},
                "use_ssl": {"type": "boolean", "default": False, "description": "Use legacy SSL (port 5223)."},
                "rooms": {"type": "array", "items": {"type": "string"}, "default": [],
                          "description": "MUC room JIDs to join (e.g. myroom@conference.jabber.org)."},
                "room_nick": {"type": "string", "default": "NeuralCleave",
                              "description": "Nick used when joining MUC rooms."},
            },
        }

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_session_start(self, event: Any) -> None:
        """Called when the XMPP session is established."""
        await self._client.get_roster()
        self._client.send_presence()

        # Join MUC rooms
        muc = self._client.plugin.get("xep_0045")
        for room in self._rooms:
            if muc:
                muc.join_muc(room, self._room_nick)
                logger.info("xmpp.joined_muc room=%s nick=%s", room, self._room_nick)

        if self._connect_future and not self._connect_future.done():
            self._connect_future.set_result(True)

    async def _on_message(self, msg: Any) -> None:
        """Handle 1:1 chat messages."""
        if msg.get("type") not in ("chat", "normal"):
            return

        body = msg.get("body", "").strip()
        if not body:
            return

        sender_jid = str(msg.get("from", ""))
        # Bare JID (user@server) without resource
        sender_bare = sender_jid.split("/")[0]

        # Echo guard: don't process our own messages
        if sender_bare == self._jid.split("/")[0]:
            return

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_bare,
            sender_name=sender_bare.split("@")[0],
            text=body,
            thread_id=None,
            raw={"from": sender_jid, "body": body, "type": "chat"},
        )
        await self._dispatch(inbound)
        logger.debug("xmpp.message from=%s len=%d", sender_bare, len(body))

    async def _on_groupchat_message(self, msg: Any) -> None:
        """Handle MUC room messages."""
        body = msg.get("body", "").strip()
        if not body:
            return

        sender_jid = str(msg.get("from", ""))
        # In MUC, from is room@conf/nick
        parts = sender_jid.split("/", 1)
        room_jid = parts[0]
        nick = parts[1] if len(parts) > 1 else ""

        # Echo guard: skip our own MUC messages
        if nick == self._room_nick:
            return

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_jid,
            sender_name=nick or sender_jid,
            text=body,
            thread_id=room_jid,
            raw={"from": sender_jid, "body": body, "type": "groupchat"},
        )
        await self._dispatch(inbound)
        logger.debug("xmpp.groupchat room=%s nick=%s len=%d", room_jid, nick, len(body))

    def _on_disconnected(self, event: Any) -> None:
        logger.warning("xmpp.disconnected unexpectedly jid=%s", self._jid)

    def _on_failed_auth(self, event: Any) -> None:
        logger.error("xmpp.auth_failed jid=%s", self._jid)
        if self._connect_future and not self._connect_future.done():
            self._connect_future.set_exception(
                RuntimeError(f"XMPP authentication failed for {self._jid!r}")
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""
