"""Entry point for the PyInstaller-bundled desktop backend sidecar.

When NeuralCleave is installed as a desktop app, Tauri spawns this
executable automatically on startup and kills it on exit.  It starts
the FastAPI/WebSocket gateway on the configured port (default 7432).

The user's config is loaded from ``~/.neuralcleave/config.toml`` when it
exists; otherwise a set of minimal defaults is used so the app works
out-of-the-box without a config wizard.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("NeuralCleave.desktop")


def _default_config_path() -> Path:
    return Path.home() / ".neuralcleave" / "config.toml"


def main() -> None:
    # Allow the Tauri side to override the port via env var for future
    # multi-instance support, otherwise fall back to the config or 7432.
    port_override = os.environ.get("NeuralCleave_PORT")

    config_path = _default_config_path()

    try:
        from neuralcleave.config import load_config

        cfg = load_config(str(config_path) if config_path.exists() else None)
    except Exception as exc:
        logger.warning("Could not load config (%s); using defaults", exc)
        from neuralcleave.config import NeuralCleaveConfig

        cfg = NeuralCleaveConfig()

    if port_override:
        try:
            cfg.gateway.port = int(port_override)
        except ValueError:
            logger.warning("Invalid NeuralCleave_PORT=%r — using config value", port_override)

    logger.info(
        "NeuralCleave desktop backend starting on %s:%s",
        cfg.gateway.bind,
        cfg.gateway.port,
    )

    # Graceful shutdown on SIGTERM (sent by Tauri on app exit)
    def _handle_sigterm(_signum: int, _frame: object) -> None:
        logger.info("SIGTERM received — shutting down")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    from neuralcleave.gateway.main import run

    run(cfg)


if __name__ == "__main__":
    main()
