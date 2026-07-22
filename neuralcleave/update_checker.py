"""Self-update support for the `neuralcleave update` CLI command.

Checks PyPI's JSON API for the latest published version of a package
and compares it against the currently installed version. Network
failures (offline, package not yet published, PyPI down) degrade to
returning None rather than raising — `neuralcleave update` should never crash
just because connectivity is unavailable.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a tuple of ints for comparison.

    Non-numeric suffixes (e.g. "2.0.0-beta", "1.2.3rc1") are truncated to
    their leading digit run; a segment with no leading digits becomes 0.
    """
    parts: list[int] = []
    for segment in version.split("."):
        match = re.match(r"\d+", segment)
        parts.append(int(match.group()) if match else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """True if *latest* is a strictly newer version than *current*."""
    return parse_version(latest) > parse_version(current)


async def get_latest_version(package: str, timeout: float = 5.0) -> str | None:
    """Fetch the latest published version of *package* from PyPI.

    Returns None on any failure (offline, package not found, malformed
    response) instead of raising.
    """
    try:
        import httpx
    except ImportError:
        logger.warning("update_checker: httpx not installed, cannot check for updates")
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_PYPI_JSON_URL.format(package=package))
            resp.raise_for_status()
            data = resp.json()
            return data["info"]["version"]
    except Exception as exc:
        logger.warning("update_checker: failed to check latest version: %s", exc)
        return None
