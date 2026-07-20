"""CanvasBlock — data model for a single rendered canvas block.

Block types
-----------
text      — plain text paragraph
markdown  — markdown string (rendered client-side)
image     — base64-encoded PNG/JPEG data URI or https:// URL
table     — {"headers": [...], "rows": [[...], ...]}
code      — {"code": "...", "language": "python"}
chart     — {"chart_type": "bar"|"line"|"pie", "labels": [...], "values": [...]}
html      — raw HTML snippet (sandboxed in client iframe)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

BLOCK_TYPES: frozenset[str] = frozenset(
    {"text", "markdown", "image", "table", "code", "chart", "html"}
)


@dataclass
class CanvasBlock:
    """A single content block on the live canvas."""

    id: str
    block_type: str
    content: Any
    title: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.block_type not in BLOCK_TYPES:
            raise ValueError(
                f"Unknown block_type {self.block_type!r}. "
                f"Allowed: {sorted(BLOCK_TYPES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "block_type": self.block_type,
            "content": self.content,
            "title": self.title,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanvasBlock":
        return cls(
            id=data.get("id", ""),
            block_type=data.get("block_type", "text"),
            content=data.get("content", ""),
            title=data.get("title", ""),
            created_at=data.get("created_at", ""),
        )

    @staticmethod
    def new(block_type: str, content: Any, title: str = "") -> "CanvasBlock":
        """Create a new block with a fresh UUID and current UTC timestamp."""
        import datetime

        return CanvasBlock(
            id=uuid.uuid4().hex,
            block_type=block_type,
            content=content,
            title=title,
            created_at=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
