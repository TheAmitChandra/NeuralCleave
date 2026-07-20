"""Web Push subscription management and VAPID key generation.

Stores push subscriptions in ~/.cortexflow/push_subscriptions.json.
VAPID keys are generated on demand and cached in memory; they are NOT
persisted here — callers should store the returned keys in config if
they need them across restarts.

Spec: RFC 8292 (VAPID), W3C Push API
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_STORE_PATH = Path.home() / ".cortexflow" / "push_subscriptions.json"


@dataclass
class PushSubscription:
    """Represents a single Web Push subscription from a browser client."""

    endpoint: str
    p256dh: str
    auth: str
    user_agent: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PushSubscription":
        return cls(
            endpoint=data["endpoint"],
            p256dh=data["p256dh"],
            auth=data["auth"],
            user_agent=data.get("user_agent", ""),
            created_at=data.get("created_at", ""),
        )

    @property
    def subscription_id(self) -> str:
        """Stable identifier derived from the endpoint URL."""
        import hashlib

        return hashlib.sha256(self.endpoint.encode()).hexdigest()[:16]


@dataclass
class PushManager:
    """File-backed store for Web Push subscriptions."""

    store_path: Path = field(default_factory=lambda: _STORE_PATH)
    _subscriptions: dict[str, PushSubscription] = field(default_factory=dict, repr=False)
    _loaded: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self) -> None:
        if not self.store_path.exists():
            self._subscriptions = {}
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            self._subscriptions = {
                sid: PushSubscription.from_dict(sub) for sid, sub in raw.items()
            }
        except Exception:
            log.warning("push_subscriptions.json is corrupt; starting fresh")
            self._subscriptions = {}

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {sid: sub.to_dict() for sid, sub in self._subscriptions.items()}
        self.store_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, subscription: PushSubscription) -> str:
        """Persist a subscription and return its ID."""
        self._ensure_loaded()
        sid = subscription.subscription_id
        self._subscriptions[sid] = subscription
        self._save()
        return sid

    def remove(self, subscription_id: str) -> bool:
        """Delete a subscription by ID.  Returns True if it existed."""
        self._ensure_loaded()
        existed = subscription_id in self._subscriptions
        if existed:
            del self._subscriptions[subscription_id]
            self._save()
        return existed

    def get(self, subscription_id: str) -> PushSubscription | None:
        self._ensure_loaded()
        return self._subscriptions.get(subscription_id)

    def list_all(self) -> list[PushSubscription]:
        self._ensure_loaded()
        return list(self._subscriptions.values())

    def count(self) -> int:
        self._ensure_loaded()
        return len(self._subscriptions)

    def clear(self) -> None:
        """Remove all subscriptions (used in tests / admin reset)."""
        self._subscriptions = {}
        self._loaded = True
        if self.store_path.exists():
            self.store_path.write_text("{}", encoding="utf-8")


# ------------------------------------------------------------------
# VAPID key generation
# ------------------------------------------------------------------


def generate_vapid_keys() -> dict[str, str]:
    """Generate a VAPID EC P-256 key pair.

    Returns dict with ``private_key`` and ``public_key`` as
    URL-safe base64-encoded strings (no padding).

    Raises ImportError if the ``cryptography`` package is not installed.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
        )
    except ImportError as exc:
        raise ImportError(
            "The 'cryptography' package is required for VAPID key generation. "
            "Install it with: pip install cryptography"
        ) from exc

    import base64

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Raw 65-byte uncompressed public key (04 || X || Y)
    pub_bytes = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

    # Private key as raw 32-byte big-endian scalar
    priv_int = private_key.private_numbers().private_value
    priv_bytes = priv_int.to_bytes(32, "big")

    return {
        "public_key": base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode(),
        "private_key": base64.urlsafe_b64encode(priv_bytes).rstrip(b"=").decode(),
    }
