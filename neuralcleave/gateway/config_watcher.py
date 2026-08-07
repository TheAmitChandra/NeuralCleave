"""Config hot-reload watcher.

Watches ``config.toml`` for changes using ``watchfiles`` and applies a
limited subset of settings without a gateway restart:

* ``[models]`` — API keys and primary/fallback/fast model names.
* ``[gateway].api_key`` — REST auth key.

Structural settings (ports, bind address, database paths, channel tokens)
require a full restart and are intentionally excluded from hot-reload to
avoid partial reconfiguration of long-lived connections.

Usage in ``_build_lifespan``::

    watcher = ConfigWatcher(cfg, on_reload=_apply_reload)
    await watcher.start()
    ...
    await watcher.stop()

``on_reload`` receives the fresh :class:`~neuralcleave.config.NeuralCleaveConfig`
on every change.  The callback runs in the event loop and should be async.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from neuralcleave.config import NeuralCleaveConfig, load_config

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watches ``config.toml`` and calls *on_reload* when it changes.

    Args:
        config:    The currently loaded config (used to locate the file).
        on_reload: Async callable that receives the reloaded config.
        debounce_s: Seconds to wait after the last change before reloading.
                    Prevents rapid re-loads during editor saves.
    """

    def __init__(
        self,
        config: NeuralCleaveConfig,
        *,
        on_reload: Callable[[NeuralCleaveConfig], Awaitable[None]],
        debounce_s: float = 1.0,
    ) -> None:
        self._config = config
        self._on_reload = on_reload
        self._debounce_s = debounce_s
        self._task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        """Start the background watcher task."""
        self._task = asyncio.create_task(self._watch(), name="config-watcher")

    async def stop(self) -> None:
        """Cancel the watcher and await its termination."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _watch(self) -> None:
        try:
            from watchfiles import awatch  # type: ignore[import]
        except ImportError:
            logger.warning("config_watcher: watchfiles not installed — hot-reload disabled")
            return

        config_path = self._config_path()
        if config_path is None:
            logger.debug("config_watcher: no config file found — hot-reload disabled")
            return

        logger.info("config_watcher: watching %s", config_path)
        try:
            async for _ in awatch(config_path):
                await asyncio.sleep(self._debounce_s)
                try:
                    fresh = load_config(config_path)
                    logger.info("config_watcher: config reloaded from %s", config_path)
                    await self._on_reload(fresh)
                except Exception as exc:
                    logger.warning("config_watcher: reload failed (%s) — keeping previous config", exc)
        except asyncio.CancelledError:
            logger.debug("config_watcher: stopped")
        except Exception as exc:
            logger.error("config_watcher: unexpected error: %s", exc)

    def _config_path(self) -> Path | None:
        """Return the path to the current config file, if it exists."""
        candidates = [
            Path.home() / ".neuralcleave" / "config.toml",
            Path("config.toml"),
        ]
        for p in candidates:
            if p.exists():
                return p
        return None
