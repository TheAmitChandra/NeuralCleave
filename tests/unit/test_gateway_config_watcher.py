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
# ---------------------------------------------------------------------------


def test_config_path_none_when_no_file(tmp_path, monkeypatch):
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no_home")

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())
    assert watcher._config_path() is None


def test_config_path_finds_home_dot_neuralcleave(tmp_path, monkeypatch):
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    home = tmp_path / "home"
    cfg_file = home / ".neuralcleave" / "config.toml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text("[agent]\nname = 'test'\n")

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())
    assert watcher._config_path() == cfg_file


def test_config_path_finds_local_config_toml(tmp_path, monkeypatch):
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    local_cfg = tmp_path / "config.toml"
    local_cfg.write_text("[agent]\nname = 'test'\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no_home")

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())
    result = watcher._config_path()
    assert result is not None
    assert result.resolve() == local_cfg.resolve()


def test_config_path_prefers_home_over_local(tmp_path, monkeypatch):
    from neuralcleave.gateway.config_watcher import ConfigWatcher

    home = tmp_path / "home"
    home_cfg = home / ".neuralcleave" / "config.toml"
    home_cfg.parent.mkdir(parents=True)
    home_cfg.write_text("")

    local_cfg = tmp_path / "config.toml"
    local_cfg.write_text("")

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)

    watcher = ConfigWatcher(_make_cfg(), on_reload=AsyncMock())
    assert watcher._config_path() == home_cfg


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
