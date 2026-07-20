"""HubRegistry — persistent local registry of hub-installed skill packages."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from neuralcleave.hub.package import HubPackage

logger = logging.getLogger(__name__)

_DEFAULT_REGISTRY_FILE = Path.home() / ".NeuralCleave" / "hub" / "registry.json"


class HubRegistry:
    """Persistent local store of installed :class:`HubPackage` records.

    Packages are stored as JSON in ``~/.NeuralCleave/hub/registry.json``.
    The file is loaded lazily on first access and written after every
    mutation (add / remove / enable / disable).

    Thread-safety: the registry is not thread-safe — all mutations should
    come from the same event loop (FastAPI's async request handlers run
    concurrently but GIL-bound dict operations are effectively atomic).
    """

    def __init__(self, registry_file: Path | str | None = None) -> None:
        self._file: Path = (
            Path(registry_file) if registry_file else _DEFAULT_REGISTRY_FILE
        )
        self._packages: dict[str, HubPackage] = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Read operations (lazy-load on first call)
    # ------------------------------------------------------------------

    def list_packages(self) -> list[HubPackage]:
        """Return all registered packages (enabled and disabled)."""
        self._ensure_loaded()
        return list(self._packages.values())

    def search(self, query: str) -> list[HubPackage]:
        """Case-insensitive search across name, description, and tags.

        An empty *query* returns all packages.
        """
        self._ensure_loaded()
        q = query.strip().lower()
        if not q:
            return self.list_packages()
        results = []
        for pkg in self._packages.values():
            if (
                q in pkg.name.lower()
                or q in pkg.description.lower()
                or any(q in t.lower() for t in pkg.tags)
                or q in pkg.author.lower()
            ):
                results.append(pkg)
        return results

    def get(self, name: str) -> HubPackage | None:
        """Return the package named *name*, or ``None`` if not found."""
        self._ensure_loaded()
        return self._packages.get(name)

    def package_count(self) -> int:
        """Total number of registered packages."""
        self._ensure_loaded()
        return len(self._packages)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, package: HubPackage) -> None:
        """Register (or replace) a package and persist to disk."""
        self._ensure_loaded()
        self._packages[package.name] = package
        self._save()
        logger.debug("hub.registry.add name=%s version=%s", package.name, package.version)

    def remove(self, name: str) -> None:
        """Remove a package by name.

        Raises:
            KeyError: If no package with that name is registered.
        """
        self._ensure_loaded()
        if name not in self._packages:
            raise KeyError(f"No hub package named {name!r} is registered")
        del self._packages[name]
        self._save()
        logger.debug("hub.registry.remove name=%s", name)

    def enable(self, name: str) -> None:
        """Mark a package as enabled."""
        self._set_enabled(name, True)

    def disable(self, name: str) -> None:
        """Mark a package as disabled."""
        self._set_enabled(name, False)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()

    def _load(self) -> None:
        self._loaded = True
        if not self._file.exists():
            self._packages = {}
            return
        try:
            raw: Any = json.loads(self._file.read_text(encoding="utf-8"))
            self._packages = {
                item["name"]: HubPackage.from_dict(item)
                for item in (raw if isinstance(raw, list) else [])
            }
            logger.debug("hub.registry.load count=%d file=%s", len(self._packages), self._file)
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning("hub.registry.load failed (%s) — starting empty", exc)
            self._packages = {}

    def _save(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            payload = [pkg.to_dict() for pkg in self._packages.values()]
            self._file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.error("hub.registry.save failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_enabled(self, name: str, enabled: bool) -> None:
        self._ensure_loaded()
        pkg = self._packages.get(name)
        if pkg is None:
            raise KeyError(f"No hub package named {name!r} is registered")
        pkg.enabled = enabled
        self._save()
