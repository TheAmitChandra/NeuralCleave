"""WeChat Work (企业微信 / WeCom) channel adapter.

WeChat Work is Tencent's enterprise messaging platform.  This adapter
connects CortexFlow to a WeChat Work application via:

1. **Webhook receiver** — an ``aiohttp`` server that WeChat Work POSTs
   inbound messages to (plain-text mode XML).  A GET to the same endpoint
   handles the initial URL verification challenge from WeChat Work.

2. **Message sender** — uses the WeChat Work REST API (``message/send``)
   with a cached OAuth2 access token to deliver messages to users, parties,
   or tags.

Authentication / token lifecycle:
    Access tokens expire after 7200 s.  The adapter refreshes them
    automatically (60 s before expiry) via ``GET /cgi-bin/gettoken``.

Config keys:
    corpid          WeChat Work corporation ID (required)
    corpsecret      Application secret (required)
    agentid         Application agent ID, e.g. ``1000002`` (required for send)
    token           Webhook verification token set in the WeChat Work console
                    (required; leave empty to skip signature check in dev)
    bot_userid      The bot's own WeChat Work user ID; messages from this
                    user are dropped to prevent echo loops
    host            Webhook server bind host (default: ``"0.0.0.0"``)
    port            Webhook server port (default: 8092)
    webhook_path    URL path for the webhook endpoint (default:
                    ``"/webhook/wechat_work"``)

Outbound target format:
    ``touser:{userid}``    Send to a specific user (e.g. ``"touser:alice"``)
    ``toparty:{partyid}``  Send to a department/party
    ``totag:{tagid}``      Send to a tag group
    ``@all``               Broadcast to all members of the app
    Bare string            Treated as touser

Message encryption:
    This adapter uses plain-text mode (明文模式) which is available in the
    WeChat Work developer settings.  Encrypted mode (安全模式) is not yet
    supported.

Example config.toml::

    [channels.wechat_work]
    enabled     = true
    corpid      = "ENV:WECHAT_CORPID"
    corpsecret  = "ENV:WECHAT_CORPSECRET"
    agentid     = 1000002
    token       = "ENV:WECHAT_WEBHOOK_TOKEN"
    bot_userid  = "cortex_bot"
    port        = 8092
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"

# WeChat Work inbound message types that map to meaningful text
_TEXT_TYPES = frozenset({"text", "image", "voice", "video", "location", "link", "file"})


def _xml_text(elem: ET.Element, tag: str, default: str = "") -> str:
    child = elem.find(tag)
    if child is None:
        return default
    return (child.text or "").strip()


class WeChatWorkAdapter(ChannelAdapter):
    """WeChat Work adapter — webhook receiver + REST message sender."""

    channel_id = "wechat_work"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._corpid: str = config.get("corpid", "")
        self._corpsecret: str = config.get("corpsecret", "")
        self._agentid: int = int(config.get("agentid", 0))
        self._token: str = config.get("token", "")
        self._bot_userid: str = config.get("bot_userid", "")
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 8092))
        self._webhook_path: str = config.get("webhook_path", "/webhook/wechat_work")

        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._runner: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server."""
        from aiohttp import web

        app = web.Application()
        app.router.add_get(self._webhook_path, self._handle_verify)
        app.router.add_post(self._webhook_path, self._handle_message)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(
            "wechat_work.connected host=%s port=%d path=%s",
            self._host,
            self._port,
            self._webhook_path,
        )

    async def disconnect(self) -> None:
        """Stop the aiohttp webhook server."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("wechat_work.disconnected")

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
        if not self._corpid or not self._corpsecret:
            return ""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _TOKEN_URL,
                    params={"corpid": self._corpid, "corpsecret": self._corpsecret},
                    timeout=10.0,
                )
                data = resp.json()
                new_token = data.get("access_token", "")
                if not new_token:
                    logger.error("wechat_work.token_error: %s", data)
                    return ""
                self._access_token = new_token
                expires_in = int(data.get("expires_in", 7200))
                self._token_expires_at = time.time() + expires_in
                logger.info("wechat_work.token_refreshed expires_in=%d", expires_in)
                return self._access_token
        except Exception as exc:
            logger.error("wechat_work.token_refresh_error: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def _verify_signature(
        self, timestamp: str, nonce: str, signature: str
    ) -> bool:
        """Verify SHA1-based webhook signature."""
        if not self._token:
            return True
        if not signature:
            return False
        parts = sorted([self._token, timestamp, nonce])
        expected = hashlib.sha1("".join(parts).encode()).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Webhook handlers
    # ------------------------------------------------------------------

    async def _handle_verify(self, request: Any) -> Any:
        """Handle GET — WeChat Work URL verification challenge."""
        from aiohttp import web

        echostr = request.query.get("echostr", "")
        signature = request.query.get("msg_signature", "") or request.query.get("signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")

        if self._verify_signature(timestamp, nonce, signature):
            return web.Response(text=echostr)
        logger.warning("wechat_work.verify_failed")
        return web.Response(status=401, text="Invalid signature")

    async def _handle_message(self, request: Any) -> Any:
        """Handle POST — inbound XML message from WeChat Work."""
        from aiohttp import web

        signature = request.query.get("msg_signature", "") or request.query.get("signature", "")
        timestamp = request.query.get("timestamp", "")
        nonce = request.query.get("nonce", "")

        if not self._verify_signature(timestamp, nonce, signature):
            logger.warning("wechat_work.invalid_signature")
            return web.Response(status=401, text="Invalid signature")

        body = await request.read()
        try:
            root = ET.fromstring(body.decode("utf-8"))
        except ET.ParseError as exc:
            logger.warning("wechat_work.xml_parse_error: %s", exc)
            return web.Response(status=400, text="Bad XML")

        msg_type = _xml_text(root, "MsgType")
        event_type = _xml_text(root, "Event").lower()

        if msg_type == "event":
            if event_type in ("subscribe", "unsubscribe", "click", "view"):
                logger.info("wechat_work.event type=%s", event_type)
            return web.Response(text="success")

        if msg_type not in _TEXT_TYPES:
            return web.Response(text="success")

        from_user = _xml_text(root, "FromUserName")
        to_user = _xml_text(root, "ToUserName")

        if self._bot_userid and from_user == self._bot_userid:
            return web.Response(text="success")

        # Build human-readable text for non-text types
        if msg_type == "text":
            text = _xml_text(root, "Content")
        elif msg_type == "location":
            lat = _xml_text(root, "Location_X")
            lng = _xml_text(root, "Location_Y")
            label = _xml_text(root, "Label")
            text = f"[location: {label} ({lat},{lng})]"
        elif msg_type == "link":
            title = _xml_text(root, "Title")
            url = _xml_text(root, "Url")
            text = f"[link: {title} {url}]"
        else:
            text = f"[{msg_type}]"

        text = text.strip()
        if not text:
            return web.Response(text="success")

        try:
            ts = float(_xml_text(root, "CreateTime") or str(time.time()))
        except (ValueError, TypeError):
            ts = time.time()

        msg_id = _xml_text(root, "MsgId")
        agent_id = _xml_text(root, "AgentID")

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=from_user,
            sender_name=from_user,
            text=text,
            thread_id=agent_id or to_user,
            timestamp=ts,
            raw={
                "from": from_user,
                "to": to_user,
                "msg_type": msg_type,
                "msg_id": msg_id,
                "agent_id": agent_id,
            },
        )

        import asyncio

        asyncio.create_task(self._dispatch(msg))
        logger.info(
            "wechat_work.message_received from=%s type=%s",
            from_user,
            msg_type,
        )
        return web.Response(text="success")

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    def _build_send_payload(self, target: str, text: str) -> dict[str, Any]:
        """Build the send-message JSON payload for *target*."""
        payload: dict[str, Any] = {
            "msgtype": "text",
            "agentid": self._agentid,
            "text": {"content": text},
        }
        if target == "@all":
            payload["touser"] = "@all"
        elif target.startswith("touser:") or target.startswith("user:"):
            payload["touser"] = target.split(":", 1)[1]
        elif target.startswith("toparty:") or target.startswith("party:"):
            payload["toparty"] = target.split(":", 1)[1]
        elif target.startswith("totag:") or target.startswith("tag:"):
            payload["totag"] = target.split(":", 1)[1]
        else:
            payload["touser"] = target
        return payload

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Send a text message to *target*.

        Returns the target on success, ``None`` on error.
        """
        if not target:
            logger.warning("wechat_work.send: target is empty")
            return None

        token = await self._get_access_token()
        if not token:
            logger.error("wechat_work.send: no access token")
            return None

        payload = self._build_send_payload(target, text)
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _SEND_URL,
                    params={"access_token": token},
                    json=payload,
                    timeout=15.0,
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    logger.error(
                        "wechat_work.send_error target=%s errcode=%s errmsg=%s",
                        target,
                        data.get("errcode"),
                        data.get("errmsg"),
                    )
                    return None
                return target
        except Exception as exc:
            logger.error("wechat_work.send_error target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if a valid access token can be fetched."""
        return bool(await self._get_access_token())

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["corpid", "corpsecret", "agentid"],
            "properties": {
                "corpid": {
                    "type": "string",
                    "description": "WeChat Work corporation ID",
                },
                "corpsecret": {
                    "type": "string",
                    "description": "WeChat Work application secret",
                },
                "agentid": {
                    "type": "integer",
                    "description": "WeChat Work application agent ID",
                },
                "token": {
                    "type": "string",
                    "description": "Webhook verification token from WeChat Work console",
                },
                "bot_userid": {
                    "type": "string",
                    "description": "Bot's WeChat Work user ID (for echo-loop prevention)",
                },
                "host": {
                    "type": "string",
                    "default": "0.0.0.0",
                    "description": "Webhook server bind host",
                },
                "port": {
                    "type": "integer",
                    "default": 8092,
                    "description": "Webhook server port",
                },
                "webhook_path": {
                    "type": "string",
                    "default": "/webhook/wechat_work",
                    "description": "URL path for the WeChat Work webhook endpoint",
                },
            },
        }
