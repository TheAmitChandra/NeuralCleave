"""HubPackage — metadata record for a skill installed from the NeuralCleave Hub."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class HubPackage:
    """Metadata for a hub-installed skill.

    Fields are intentionally flat (no nested objects) so the record
    serialises cleanly to JSON in the registry file.
    """

    name: str
    version: str
    description: str
    author: str
    source_url: str
    install_date: str          # ISO-8601 UTC, e.g. "2026-07-14T10:00:00Z"
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    checksum: str = ""         # SHA-256 hex of downloaded source bytes
    homepage: str = ""
    license: str = "MIT"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("HubPackage.name must not be empty")
        if not _NAME_RE.match(self.name):
            raise ValueError(
                f"HubPackage.name {self.name!r} contains invalid characters "
                "(only letters, digits, hyphens, and underscores allowed)"
            )
        if not self.version:
            raise ValueError("HubPackage.version must not be empty")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "source_url": self.source_url,
            "install_date": self.install_date,
            "tags": self.tags,
            "enabled": self.enabled,
            "checksum": self.checksum,
            "homepage": self.homepage,
            "license": self.license,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HubPackage":
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            source_url=data.get("source_url", ""),
            install_date=data.get("install_date", ""),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
            checksum=data.get("checksum", ""),
            homepage=data.get("homepage", ""),
            license=data.get("license", "MIT"),
        )
