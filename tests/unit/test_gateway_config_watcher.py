"""Unit tests for neuralcleave.gateway.config_watcher.ConfigWatcher."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from neuralcleave.config import NeuralCleaveConfig


def _make_cfg() -> NeuralCleaveConfig:
    return NeuralCleaveConfig()


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_creates_task():
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    callback = AsyncMock()
    watcher = ConfigWatcher(_make_cfg(), on_reload=callback)

    # Patch _watch to return immediately so we don't block.
    with patch.object(watcher, "_watch", new_callable=AsyncMock):
        await watcher.start()
        assert watcher._task is not None
        await watcher.stop()


@pytest.mark.asyncio
async def test_stop_clears_task():
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())

    with patch.object(watcher, "_watch", new_callable=AsyncMock):
        await watcher.start()
        await watcher.stop()

    assert watcher._task is None


@pytest.mark.asyncio
async def test_stop_idempotent_before_start():
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())
    await watcher.stop()  # must not raise


@pytest.mark.asyncio
async def test_stop_idempotent_after_stop():
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())
    with patch.object(watcher, "_watch", new_callable=AsyncMock):
        await watcher.start()
        await watcher.stop()
        await watcher.stop()  # second stop — must not raise


# ---------------------------------------------------------------------------
# _config_path
#
# Round 7 gap analysis 5.2 (2026-08-30): this used to re-guess the path from
# two hard-coded candidates (~/.neuralcleave/config.toml, ./config.toml),
# ignoring whichever file load_config() actually loaded - a gateway started
# with `-c custom.toml` would silently watch the wrong file. It now trusts
# NeuralCleaveConfig.config_path, set by load_config() itself.
# ---------------------------------------------------------------------------


def test_config_path_none_when_config_path_unset():
    """The default all-defaults config (no file was loaded) has
    config_path=None, so there's nothing to watch."""
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())
    assert watcher._config_path() is None


def test_config_path_uses_the_configs_own_path(tmp_path):
    """The exact file load_config() reports loading from - not a guess."""
    from neuralcleave.config import NeuralCleaveConfig
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    custom_cfg_file = tmp_path / "custom.toml"
    custom_cfg_file.write_text("[agent]\nname = 'test'\n")

    cfg = NeuralCleaveConfig(config_path=custom_cfg_file)
    watcher = ConfigWatcher(cfg, on_reload=AsyncMock())
    assert watcher._config_path() == custom_cfg_file


def test_config_path_ignores_hardcoded_candidates_when_a_custom_path_is_set(tmp_path, monkeypatch):
    """The old candidate-guessing behavior must not leak back in - a
    gateway started with -c custom.toml must never fall back to watching
    ~/.neuralcleave/config.toml just because that file happens to exist."""
    from neuralcleave.config import NeuralCleaveConfig
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    home = tmp_path / "home"
    unrelated_home_cfg = home / ".neuralcleave" / "config.toml"
    unrelated_home_cfg.parent.mkdir(parents=True)
    unrelated_home_cfg.write_text("[security]\nrequire_shell_approval = false\n")
    monkeypatch.setattr(Path, "home", lambda: home)

    custom_cfg_file = tmp_path / "custom.toml"
    custom_cfg_file.write_text("[agent]\nname = 'test'\n")

    cfg = NeuralCleaveConfig(config_path=custom_cfg_file)
    watcher = ConfigWatcher(cfg, on_reload=AsyncMock())
    assert watcher._config_path() == custom_cfg_file


def test_config_path_none_when_the_configs_path_no_longer_exists(tmp_path):
    """A path that was valid at load time but has since been deleted must
    not be watched (watchfiles would raise on a missing path)."""
    from neuralcleave.config import NeuralCleaveConfig
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    missing = tmp_path / "deleted.toml"
    cfg = NeuralCleaveConfig(config_path=missing)
    watcher = ConfigWatcher(cfg, on_reload=AsyncMock())
    assert watcher._config_path() is None


# ---------------------------------------------------------------------------
# _watch — watchfiles absent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watch_graceful_when_watchfiles_absent():
    """_watch exits cleanly when watchfiles is not importable."""
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())

    # Simulate ImportError by replacing the function body's import path.
    import builtins

    original = builtins.__import__

    def _block_watchfiles(name, *args, **kwargs):
        if name == "watchfiles":
            raise ImportError("no module named watchfiles")
        return original(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_block_watchfiles):
        # Should return without raising.
        await asyncio.wait_for(watcher._watch(), timeout=2.0)
