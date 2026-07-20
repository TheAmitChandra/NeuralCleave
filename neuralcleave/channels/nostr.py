"""Nostr channel adapter — decentralized social protocol (NIP-01 + NIP-04).

Connects to one or more Nostr relays via WebSocket. Subscribes to NIP-04
encrypted direct messages (kind 4) addressed to the configured public key.
Replies are encrypted with NIP-04 (ECDH + AES-256-CBC) and published to
all connected relays.

No additional pip dependencies: uses only ``aiohttp`` (already required by
the gateway) and ``cryptography`` (already required for other adapters).
All secp256k1 curve math and BIP-340 Schnorr signing are implemented in
pure Python inside this module.

Auth / Identity:
    ``private_key``     32-byte secp256k1 private key as a 64-char lowercase
                        hex string.  Generate one with::

                            python -c "import secrets; print(secrets.token_hex(32))"

                        The corresponding public key (Nostr npub) is derived
                        automatically.

Config keys:
    private_key         64-char hex secp256k1 private key (required)
    relay_urls          list of relay WebSocket URLs (default:
                        ``["wss://relay.damus.io", "wss://nos.lol"]``)
    subscribe_kinds     list of Nostr event kinds to receive (default: ``[4]``,
                        NIP-04 encrypted DMs)
    reconnect_delay     seconds between reconnect attempts (default: 5.0)
    ping_relay          relay URL used for ``ping()``; defaults to the first
                        entry in ``relay_urls``

Outbound target format:
    Recipient's public key as a 64-char lowercase hex string (Nostr npub
    decoded, not the ``npub1…`` bech32 form).

Example config.toml::

    [channels.nostr]
    enabled     = true
    private_key = "ENV:NOSTR_PRIVATE_KEY"
    relay_urls  = [
        "wss://relay.damus.io",
        "wss://nos.lol",
        "wss://relay.snort.social",
    ]
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any

from neuralcleave.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# secp256k1 curve parameters
# ---------------------------------------------------------------------------

_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
_Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
_G = (_Gx, _Gy)

_Point = tuple[int, int] | None


def _point_add(P: _Point, Q: _Point) -> _Point:
    """Add two secp256k1 points (None = point at infinity)."""
    if P is None:
        return Q
    if Q is None:
        return P
    if P[0] == Q[0]:
        if P[1] != Q[1]:
            return None
        lam = (3 * P[0] * P[0] * pow(2 * P[1], _P - 2, _P)) % _P
    else:
        lam = ((Q[1] - P[1]) * pow(Q[0] - P[0], _P - 2, _P)) % _P
    x = (lam * lam - P[0] - Q[0]) % _P
    y = (lam * (P[0] - x) - P[1]) % _P
    return (x, y)


def _point_mul(n: int, P: _Point = None) -> _Point:
    """Scalar multiplication on secp256k1 (defaults to generator point)."""
    if P is None:
        P = _G
    R: _Point = None
    while n:
        if n & 1:
            R = _point_add(R, P)
        P = _point_add(P, P)
        n >>= 1
    return R


def _lift_x(x: int) -> _Point:
    """Return the secp256k1 point with the given x and even y (BIP-340)."""
    y_sq = (pow(x, 3, _P) + 7) % _P
    y = pow(y_sq, (_P + 1) // 4, _P)
    if pow(y, 2, _P) != y_sq:
        return None
    return (x, y if y % 2 == 0 else _P - y)


def _privkey_to_pubkey_hex(privkey_hex: str) -> str:
    """Derive the 32-byte BIP-340 public key (x-coordinate only) as hex."""
    sk = int(privkey_hex, 16)
    P = _point_mul(sk)
    if P is None:
        raise ValueError("private key maps to point at infinity")
    return f"{P[0]:064x}"


# ---------------------------------------------------------------------------
# BIP-340 Schnorr signing
# ---------------------------------------------------------------------------


def _tagged_hash(tag: str, data: bytes) -> bytes:
    """BIP-340 tagged SHA256: SHA256(SHA256(tag) || SHA256(tag) || data)."""
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


def _schnorr_sign(msg: bytes, privkey_hex: str, aux: bytes | None = None) -> bytes:
    """Return a 64-byte BIP-340 Schnorr signature over *msg*.

    *msg* must be 32 bytes (the Nostr event id bytes).
    *aux* is 32 bytes of auxiliary randomness; defaults to ``os.urandom(32)``.
    """
    if aux is None:
        aux = secrets.token_bytes(32)
    a = int(privkey_hex, 16)
    P = _point_mul(a)
    if P is None:
        raise ValueError("invalid private key")
    if P[1] % 2 != 0:
        a = _N - a
    t = a ^ int.from_bytes(_tagged_hash("BIP0340/aux", aux), "big")
    t_b = t.to_bytes(32, "big")
    p_b = P[0].to_bytes(32, "big")
    k = int.from_bytes(_tagged_hash("BIP0340/nonce", t_b + p_b + msg), "big") % _N
    if k == 0:
        raise ValueError("nonce is zero")
    R = _point_mul(k)
    if R is None:
        raise ValueError("R is point at infinity")
    if R[1] % 2 != 0:
        k = _N - k
    r_b = R[0].to_bytes(32, "big")
    e = int.from_bytes(_tagged_hash("BIP0340/challenge", r_b + p_b + msg), "big") % _N
    s = (k + e * a) % _N
    return r_b + s.to_bytes(32, "big")


def _schnorr_verify(msg: bytes, pubkey_hex: str, sig: bytes) -> bool:
    """Return True if *sig* is a valid BIP-340 Schnorr signature."""
    try:
        if len(sig) != 64:
            return False
        P = _lift_x(int(pubkey_hex, 16))
        if P is None:
            return False
        r = int.from_bytes(sig[:32], "big")
        s = int.from_bytes(sig[32:], "big")
        if r >= _P or s >= _N:
            return False
        p_b = P[0].to_bytes(32, "big")
        r_b = sig[:32]
        e = int.from_bytes(_tagged_hash("BIP0340/challenge", r_b + p_b + msg), "big") % _N
        R = _point_add(_point_mul(s), _point_mul(_N - e, P))
        if R is None or R[1] % 2 != 0 or R[0] != r:
            return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# NIP-04 DM encryption / decryption
# ---------------------------------------------------------------------------


def _ecdh_shared_x(privkey_hex: str, pubkey_hex: str) -> bytes:
    """Compute the NIP-04 ECDH shared secret (x-coordinate, 32 bytes)."""
    sk = int(privkey_hex, 16)
    peer = _lift_x(int(pubkey_hex, 16))
    if peer is None:
        raise ValueError(f"invalid pubkey: {pubkey_hex}")
    shared = _point_mul(sk, peer)
    if shared is None:
        raise ValueError("ECDH produced point at infinity")
    return shared[0].to_bytes(32, "big")


def _nip04_encrypt(privkey_hex: str, recipient_pubkey_hex: str, plaintext: str) -> str:
    """Return NIP-04 encrypted content: ``base64(ct)?iv=base64(iv)``."""
    from cryptography.hazmat.primitives import padding as _pad
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    shared = _ecdh_shared_x(privkey_hex, recipient_pubkey_hex)
    iv = os.urandom(16)
    padder = _pad.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(shared), modes.CBC(iv)).encryptor()
    ct = enc.update(padded) + enc.finalize()
    return base64.b64encode(ct).decode() + "?iv=" + base64.b64encode(iv).decode()


def _nip04_decrypt(privkey_hex: str, sender_pubkey_hex: str, content: str) -> str:
    """Decrypt a NIP-04 content string and return the plaintext."""
    from cryptography.hazmat.primitives import padding as _pad
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    parts = content.split("?iv=")
    if len(parts) != 2:
        raise ValueError("invalid NIP-04 content: missing ?iv=")
    ct = base64.b64decode(parts[0])
    iv = base64.b64decode(parts[1])
    shared = _ecdh_shared_x(privkey_hex, sender_pubkey_hex)
    dec = Cipher(algorithms.AES(shared), modes.CBC(iv)).decryptor()
    padded = dec.update(ct) + dec.finalize()
    unpadder = _pad.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


# ---------------------------------------------------------------------------
# Nostr event helpers
# ---------------------------------------------------------------------------


def _event_id(event: dict[str, Any]) -> str:
    """Return the SHA256 hex digest of the canonical Nostr event serialisation."""
    serialized = json.dumps(
        [0, event["pubkey"], event["created_at"], event["kind"], event["tags"], event["content"]],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _sign_event(event: dict[str, Any], privkey_hex: str) -> dict[str, Any]:
    """Return a copy of *event* with ``id`` and ``sig`` fields filled in."""
    eid = _event_id(event)
    sig = _schnorr_sign(bytes.fromhex(eid), privkey_hex)
    return {**event, "id": eid, "sig": sig.hex()}


def _build_dm_event(
    sender_privkey_hex: str,
    sender_pubkey_hex: str,
    recipient_pubkey_hex: str,
    plaintext: str,
) -> dict[str, Any]:
    """Create a signed NIP-04 kind-4 DM event."""
    content = _nip04_encrypt(sender_privkey_hex, recipient_pubkey_hex, plaintext)
    event: dict[str, Any] = {
        "pubkey": sender_pubkey_hex,
        "created_at": int(time.time()),
        "kind": 4,
        "tags": [["p", recipient_pubkey_hex]],
        "content": content,
    }
    return _sign_event(event, sender_privkey_hex)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class NostrAdapter(ChannelAdapter):
    """Nostr adapter — NIP-04 encrypted DMs over relay WebSocket connections."""

    channel_id = "nostr"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._private_key_hex: str = config.get("private_key", "")

        relay_urls = config.get("relay_urls", ["wss://relay.damus.io", "wss://nos.lol"])
        if isinstance(relay_urls, str):
            relay_urls = [relay_urls]
        self._relay_urls: list[str] = list(relay_urls)

        self._subscribe_kinds: list[int] = list(config.get("subscribe_kinds", [4]))
        self._reconnect_delay: float = float(config.get("reconnect_delay", 5.0))
        ping_relay = config.get("ping_relay", "")
        self._ping_relay: str = ping_relay or (self._relay_urls[0] if self._relay_urls else "")

        self._public_key_hex: str = ""
        if self._private_key_hex:
            try:
                self._public_key_hex = _privkey_to_pubkey_hex(self._private_key_hex)
            except Exception as exc:
                logger.error("nostr.init: bad private_key: %s", exc)

        self._ws_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._relay_tasks: list[asyncio.Task[None]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to all configured relays and start listening for events."""
        self._stop_event = asyncio.Event()
        self._ws_task = asyncio.create_task(self._run_all_relays())
        logger.info(
            "nostr.connected pubkey=%s relays=%s",
            self._public_key_hex[:16] if self._public_key_hex else "none",
            self._relay_urls,
        )

    async def disconnect(self) -> None:
        """Disconnect from all relays and stop all background tasks."""
        if self._stop_event:
            self._stop_event.set()
        for task in list(self._relay_tasks):
            task.cancel()
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except (asyncio.CancelledError, Exception):
                pass
        self._ws_task = None
        self._relay_tasks.clear()
        logger.info("nostr.disconnected")

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
        """Send a NIP-04 encrypted DM to *target* (recipient pubkey hex).

        Returns the event id on success, ``None`` on error.
        """
        if not target:
            logger.warning("nostr.send: target is empty")
            return None
        if not self._private_key_hex or not self._public_key_hex:
            logger.error("nostr.send: private_key not configured")
            return None
        try:
            event = _build_dm_event(
                self._private_key_hex,
                self._public_key_hex,
                target,
                text,
            )
        except Exception as exc:
            logger.error("nostr.send: event creation failed: %s", exc)
            return None
        return await self._broadcast_event(event)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if a WebSocket connection to the ping relay succeeds."""
        if not self._ping_relay:
            return False
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    self._ping_relay,
                    timeout=aiohttp.ClientTimeout(connect=5.0),
                ) as ws:
                    await ws.send_json(["REQ", "ping_check", {"limit": 1}])
                    return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Relay background loop
    # ------------------------------------------------------------------

    async def _run_all_relays(self) -> None:
        """Run per-relay connection loops concurrently inside one aiohttp session."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            tasks = [
                asyncio.create_task(self._relay_loop(url, session))
                for url in self._relay_urls
            ]
            self._relay_tasks = tasks
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                for t in tasks:
                    t.cancel()

    async def _relay_loop(self, relay_url: str, session: Any) -> None:
        """Maintain a persistent connection to a single relay, reconnecting on error."""
        import aiohttp

        sub_id = f"cf_{self._public_key_hex[:16] if self._public_key_hex else 'nokey'}"
        while self._stop_event and not self._stop_event.is_set():
            try:
                async with session.ws_connect(
                    relay_url,
                    timeout=aiohttp.ClientTimeout(connect=10.0),
                    heartbeat=30.0,
                ) as ws:
                    logger.info("nostr.relay_connected url=%s", relay_url)
                    filters: dict[str, Any] = {"kinds": self._subscribe_kinds}
                    if self._public_key_hex:
                        filters["#p"] = [self._public_key_hex]
                    await ws.send_json(["REQ", sub_id, filters])

                    async for raw in ws:
                        if self._stop_event.is_set():
                            break
                        if raw.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(raw.data)
                                await self._handle_relay_message(data)
                            except Exception as exc:
                                logger.debug("nostr.relay_parse_error: %s", exc)
                        elif raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break

                    logger.info("nostr.relay_disconnected url=%s", relay_url)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("nostr.relay_error url=%s: %s", relay_url, exc)

            if self._stop_event and not self._stop_event.is_set():
                await asyncio.sleep(self._reconnect_delay)

    # ------------------------------------------------------------------
    # Relay message handling
    # ------------------------------------------------------------------

    async def _handle_relay_message(self, data: Any) -> None:
        """Dispatch a parsed relay message array."""
        if not isinstance(data, list) or not data:
            return
        msg_type = data[0]
        if msg_type == "EVENT" and len(data) >= 3:
            await self._process_event(data[2])
        elif msg_type == "NOTICE" and len(data) >= 2:
            logger.info("nostr.relay_notice: %s", data[1])

    async def _process_event(self, event: Any) -> None:
        """Parse a Nostr event, decrypt kind-4 DMs, and dispatch InboundMessage."""
        if not isinstance(event, dict):
            return

        kind = event.get("kind")
        pubkey = event.get("pubkey", "")
        content = event.get("content", "")
        event_id = event.get("id", "")

        if pubkey == self._public_key_hex:
            return

        if kind == 4:
            if not self._private_key_hex or not content:
                return
            try:
                text = _nip04_decrypt(self._private_key_hex, pubkey, content)
            except Exception as exc:
                logger.debug("nostr.decrypt_error event=%s: %s", event_id, exc)
                return
        else:
            text = content

        text = text.strip()
        if not text:
            return

        ts = float(event.get("created_at", time.time()))
        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=pubkey,
            sender_name=pubkey[:16] if pubkey else "unknown",
            text=text,
            thread_id=event_id or pubkey,
            timestamp=ts,
            raw=event,
        )
        asyncio.create_task(self._dispatch(msg))

    # ------------------------------------------------------------------
    # Event broadcasting
    # ------------------------------------------------------------------

    async def _broadcast_event(self, event: dict[str, Any]) -> str | None:
        """Publish *event* to all configured relays.

        Returns the event id if at least one relay accepted the event.
        """
        if not self._relay_urls:
            return None

        import aiohttp

        sent = False
        try:
            async with aiohttp.ClientSession() as session:
                for relay_url in self._relay_urls:
                    try:
                        async with session.ws_connect(
                            relay_url,
                            timeout=aiohttp.ClientTimeout(connect=10.0),
                        ) as ws:
                            await ws.send_json(["EVENT", event])
                            try:
                                async with asyncio.timeout(5.0):
                                    async for raw in ws:
                                        if raw.type == aiohttp.WSMsgType.TEXT:
                                            resp = json.loads(raw.data)
                                            if (
                                                isinstance(resp, list)
                                                and len(resp) >= 3
                                                and resp[0] == "OK"
                                            ):
                                                if resp[2]:
                                                    sent = True
                                                break
                                        elif raw.type in (
                                            aiohttp.WSMsgType.CLOSED,
                                            aiohttp.WSMsgType.ERROR,
                                        ):
                                            break
                            except (asyncio.TimeoutError, TimeoutError):
                                sent = True
                    except Exception as exc:
                        logger.warning("nostr.broadcast_relay_error relay=%s: %s", relay_url, exc)
        except Exception as exc:
            logger.error("nostr.broadcast_error: %s", exc)
            return None

        return event["id"] if sent else None

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["private_key"],
            "properties": {
                "private_key": {
                    "type": "string",
                    "description": "32-byte secp256k1 private key as 64-char lowercase hex",
                },
                "relay_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["wss://relay.damus.io", "wss://nos.lol"],
                    "description": "List of Nostr relay WebSocket URLs",
                },
                "subscribe_kinds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "default": [4],
                    "description": "Nostr event kinds to subscribe to (4 = NIP-04 DMs)",
                },
                "reconnect_delay": {
                    "type": "number",
                    "default": 5.0,
                    "description": "Seconds between relay reconnect attempts",
                },
                "ping_relay": {
                    "type": "string",
                    "description": "Relay URL for ping() health check (defaults to first relay_url)",
                },
            },
        }
