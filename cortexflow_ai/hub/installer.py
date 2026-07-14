"""HubInstaller — download, scan, and install skill packages from the hub."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from cortexflow_ai.hub.package import HubPackage
from cortexflow_ai.hub.registry import HubRegistry
from cortexflow_ai.hub.scanner import PackageScanner, ScanResult

logger = logging.getLogger(__name__)

_DEFAULT_HUB_DIR = Path.home() / ".cortexflow" / "hub"


class InstallError(RuntimeError):
    """Raised when a hub install fails for any reason."""


class ScanBlockedError(InstallError):
    """Raised when the safety scanner blocks installation."""


class HubInstaller:
    """Downloads, scans, writes, and activates hub skill packages.

    Install flow
    ------------
    1. Fetch source code from *source_url* (https or data URI).
    2. Run :class:`~cortexflow_ai.hub.scanner.PackageScanner`.
    3. If scan fails and ``force=False``, raise :class:`ScanBlockedError`.
    4. Persist code to ``~/.cortexflow/hub/skills/<name>/skill.py``.
    5. Delegate to ``SkillWriter.write_skill()`` — validates, loads module,
       registers with ``PluginRegistry``.
    6. Record package in :class:`~cortexflow_ai.hub.registry.HubRegistry`.

    Uninstall flow
    --------------
    1. Delegate to ``SkillWriter.delete_skill(name)`` — unregisters from
       plugin registry and removes ``~/.cortexflow/skills/<name>/`` directory.
    2. Remove package record from :class:`HubRegistry`.

    Args:
        hub_dir:         Base directory for hub data (defaults to
                         ``~/.cortexflow/hub/``).
        registry:        :class:`HubRegistry` instance.  Created fresh if
                         not provided.
        skill_writer:    ``SkillWriter`` instance for persisting and loading
                         skill code.  Created fresh if not provided (no live
                         plugin registry attached — hot-reload only works when
                         a real registry is injected).
        plugin_registry: ``PluginRegistry`` for hot-reload after install.
                         Optional — installation still works without it.
        scanner:         :class:`PackageScanner` instance.  Created fresh if
                         not provided.
    """

    def __init__(
        self,
        hub_dir: Path | str | None = None,
        registry: HubRegistry | None = None,
        skill_writer: Any = None,
        plugin_registry: Any = None,
        scanner: PackageScanner | None = None,
    ) -> None:
        self._hub_dir = Path(hub_dir) if hub_dir else _DEFAULT_HUB_DIR
        self._registry = registry or HubRegistry()
        self._skill_writer = skill_writer
        self._plugin_registry = plugin_registry
        self._scanner = scanner or PackageScanner()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def install(
        self,
        source_url: str,
        *,
        name: str | None = None,
        version: str = "1.0.0",
        description: str = "",
        author: str = "",
        tags: list[str] | None = None,
        force: bool = False,
    ) -> HubPackage:
        """Install a skill from *source_url*.

        Args:
            source_url: URL of the skill source.  Supported schemes:
                        ``https://`` (raw .py file), ``data:text/plain,...``
                        (inline code, useful for testing).
            name:       Override the package name.  If omitted, inferred
                        from the URL's last path segment (stem).
            version:    Package version string.
            description: Human-readable description.
            author:     Author name.
            tags:       List of searchable tags.
            force:      If ``True``, install even if the scanner flags errors.

        Returns:
            The registered :class:`HubPackage`.

        Raises:
            InstallError: On fetch failures, name collisions, or I/O errors.
            ScanBlockedError: If the scanner blocks the code and ``force``
                              is ``False``.
        """
        code = await self._fetch_code(source_url)
        pkg_name = self._resolve_name(name, source_url)

        if not force and self._registry.get(pkg_name) is not None:
            raise InstallError(
                f"Package {pkg_name!r} is already installed. "
                "Pass force=True to reinstall."
            )

        scan_result = self._scanner.scan_code(code, filename=f"{pkg_name}.py")
        if not scan_result.safe and not force:
            raise ScanBlockedError(
                f"PackageScanner blocked installation of {pkg_name!r}: "
                + "; ".join(scan_result.errors)
            )
        if scan_result.errors and force:
            logger.warning(
                "hub.install force=True, bypassing scanner errors: %s",
                scan_result.errors,
            )

        checksum = hashlib.sha256(code.encode()).hexdigest()

        self._write_skill(pkg_name, code, description)

        package = HubPackage(
            name=pkg_name,
            version=version,
            description=description,
            author=author,
            source_url=source_url,
            install_date=self._now_iso(),
            tags=tags or [],
            enabled=True,
            checksum=checksum,
        )
        self._registry.add(package)
        logger.info("hub.install name=%s version=%s", pkg_name, version)
        return package

    def uninstall(self, name: str) -> None:
        """Remove an installed hub package.

        Args:
            name: Package name as recorded in the registry.

        Raises:
            InstallError: If the package is not found in the registry.
        """
        if self._registry.get(name) is None:
            raise InstallError(f"No hub package named {name!r} is installed")

        if self._skill_writer is not None:
            try:
                self._skill_writer.delete_skill(name)
            except Exception as exc:
                logger.warning("hub.uninstall skill_writer.delete_skill failed: %s", exc)

        try:
            self._registry.remove(name)
        except KeyError:
            pass

        logger.info("hub.uninstall name=%s", name)

    def scan_url(self, source_url: str) -> ScanResult:
        """Fetch and scan *source_url* without installing.

        Synchronous wrapper — fetches code synchronously for CLI use.
        Use ``await installer.install(url)`` for the async path.
        """
        import asyncio
        code = asyncio.get_event_loop().run_until_complete(self._fetch_code(source_url))
        return self._scanner.scan_code(code)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch_code(self, source_url: str) -> str:
        """Fetch source code from *source_url* and return as a string."""
        if source_url.startswith("data:"):
            return self._decode_data_uri(source_url)

        if source_url.startswith(("http://", "https://")):
            try:
                import httpx
                async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                    resp = await client.get(source_url)
                    resp.raise_for_status()
                    return resp.text
            except Exception as exc:
                raise InstallError(f"Failed to fetch {source_url!r}: {exc}") from exc

        raise InstallError(
            f"Unsupported URL scheme in {source_url!r}. "
            "Supported: https://, data:text/plain,..."
        )

    @staticmethod
    def _decode_data_uri(uri: str) -> str:
        """Decode a ``data:text/plain[;base64],<content>`` URI."""
        _, rest = uri.split(",", 1)
        if ";base64" in uri.split(",")[0]:
            import base64
            return base64.b64decode(rest).decode()
        from urllib.parse import unquote
        return unquote(rest)

    @staticmethod
    def _resolve_name(name: str | None, source_url: str) -> str:
        """Return *name* if given, else derive from the URL's path stem."""
        if name:
            return name.strip()
        from pathlib import PurePosixPath
        stem = PurePosixPath(source_url.split("?")[0]).stem
        # Sanitise: replace hyphens/dots → underscores, drop other non-alphanum
        stem = stem.replace("-", "_").replace(".", "_")
        import re
        stem = re.sub(r"[^A-Za-z0-9_]", "", stem) or "hub_skill"
        return stem

    def _write_skill(self, name: str, code: str, description: str) -> None:
        """Write skill code to disk and load into the plugin registry."""
        if self._skill_writer is not None:
            try:
                self._skill_writer.write_skill(name, code, description)
                return
            except Exception as exc:
                raise InstallError(
                    f"SkillWriter failed to install {name!r}: {exc}"
                ) from exc

        # Fallback when no SkillWriter injected: write to skills dir directly
        skills_dir = Path.home() / ".cortexflow" / "skills" / name
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "skill.py").write_text(code, encoding="utf-8")

    @staticmethod
    def _now_iso() -> str:
        import datetime
        return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
