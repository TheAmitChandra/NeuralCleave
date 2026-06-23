"""Unit tests for cortexflow.cli — status, channels add/remove, memory clear, config edit."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

import cortexflow.cli as cli_module
from cortexflow.cli import (
    _channel_detail,
    _channel_status,
    _is_process_running,
    _pidfile_path,
    _read_pidfile,
    _set_channel_enabled,
    cli,
)
from cortexflow.config import ChannelConfig

# ---------------------------------------------------------------------------
# _channel_status / _channel_detail
# ---------------------------------------------------------------------------


def test_channel_status_not_configured_when_missing():
    assert _channel_status({}, "telegram") == "not configured"


def test_channel_status_none_dict():
    assert _channel_status(None, "telegram") == "not configured"


def test_channel_status_enabled():
    cfg = {"telegram": ChannelConfig(enabled=True)}
    assert _channel_status(cfg, "telegram") == "enabled"


def test_channel_status_disabled():
    cfg = {"telegram": ChannelConfig(enabled=False)}
    assert _channel_status(cfg, "telegram") == "disabled"


def test_channel_detail_fallback_when_missing():
    assert _channel_detail({}, "telegram", "fallback text") == "fallback text"


def test_channel_detail_redacts_secrets():
    cfg = {"telegram": ChannelConfig(enabled=True, extra={"bot_token": "secret123"})}
    detail = _channel_detail(cfg, "telegram", "fallback")
    assert "secret123" not in detail
    assert "bot_token=***" in detail


def test_channel_detail_shows_plain_values():
    cfg = {"telegram": ChannelConfig(enabled=True, extra={"chat_id": "12345"})}
    detail = _channel_detail(cfg, "telegram", "fallback")
    assert "chat_id=12345" in detail


# ---------------------------------------------------------------------------
# _set_channel_enabled
# ---------------------------------------------------------------------------


def test_set_channel_enabled_raises_if_no_config(tmp_path: Path):
    missing = tmp_path / "nope.toml"
    with pytest.raises(Exception):
        _set_channel_enabled(missing, "telegram", enabled=True)


def test_set_channel_enabled_appends_new_section(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")

    _set_channel_enabled(config_file, "telegram", enabled=True)

    text = config_file.read_text(encoding="utf-8")
    assert "[channels.telegram]" in text
    assert "enabled = true" in text


def test_set_channel_enabled_updates_existing_section(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[channels.telegram]\nenabled = false\nbot_token = "tok"\n',
        encoding="utf-8",
    )

    _set_channel_enabled(config_file, "telegram", enabled=True)

    text = config_file.read_text(encoding="utf-8")
    assert "enabled = true" in text
    assert "enabled = false" not in text
    assert 'bot_token = "tok"' in text  # other keys preserved


def test_set_channel_enabled_toggle_roundtrip(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")

    _set_channel_enabled(config_file, "slack", enabled=True)
    assert "enabled = true" in config_file.read_text(encoding="utf-8")

    _set_channel_enabled(config_file, "slack", enabled=False)
    assert "enabled = false" in config_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI integration — status / channels add/remove / memory clear
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_status_command_runs(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "TestBot"\n', encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "status"])

    assert result.exit_code == 0
    assert "TestBot" in result.output
    assert "Long-term memory rows" in result.output


def test_status_no_memory_db_shows_zero(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "TestBot"\n', encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "status"])

    assert result.exit_code == 0
    assert "0" in result.output


def test_channels_add_command(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "channels", "add", "discord"])

    assert result.exit_code == 0
    assert "Enabled" in result.output
    assert "enabled = true" in config_file.read_text(encoding="utf-8")


def test_channels_remove_command(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "[channels.discord]\nenabled = true\n", encoding="utf-8"
    )

    result = runner.invoke(cli, ["-c", str(config_file), "channels", "remove", "discord"])

    assert result.exit_code == 0
    assert "Disabled" in result.output
    assert "enabled = false" in config_file.read_text(encoding="utf-8")


def test_channels_add_missing_config_errors(tmp_path: Path, runner: CliRunner):
    missing = tmp_path / "nope.toml"

    result = runner.invoke(cli, ["-c", str(missing), "channels", "add", "discord"])

    assert result.exit_code != 0


def test_memory_clear_aborts_without_yes(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "clear"], input="n\n")

    assert result.exit_code == 0
    assert "Aborted" in result.output


def test_memory_clear_with_yes_flag(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(
        f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8"
    )

    from cortexflow.memory.long_term import LongTermMemory

    async def _seed() -> None:
        lt = LongTermMemory(db_path=str(db_path))
        await lt.init_schema()
        await lt.store("s1", "remember this", 0.9)

    asyncio.run(_seed())

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "clear", "--yes"])

    assert result.exit_code == 0
    assert "Cleared 1 memory entry" in result.output


# ---------------------------------------------------------------------------
# memory search — --tag filter and cross-session search
# ---------------------------------------------------------------------------


def _seed_memory(db_path: Path) -> None:
    from cortexflow.memory.long_term import LongTermMemory

    async def _seed() -> None:
        lt = LongTermMemory(db_path=str(db_path))
        await lt.init_schema()
        await lt.store("session-A", "deploying with #docker today", 0.6)
        await lt.store("session-B", "shared keyword alpha", 0.5)

    asyncio.run(_seed())


def test_memory_search_by_tag(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")
    _seed_memory(db_path)

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "search", "", "--tag", "docker"])

    assert result.exit_code == 0
    assert "docker" in result.output
    assert "session-A" in result.output


def test_memory_search_without_session_searches_all(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")
    _seed_memory(db_path)

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "search", "keyword alpha"])

    assert result.exit_code == 0
    assert "session-B" in result.output


# ---------------------------------------------------------------------------
# _pidfile_path / _read_pidfile / _is_process_running
# ---------------------------------------------------------------------------


def test_pidfile_path_uses_config_dir(tmp_path: Path):
    config_file = tmp_path / "sub" / "config.toml"
    assert _pidfile_path(str(config_file)) == config_file.parent / "cortex.pid"


def test_pidfile_path_defaults_when_no_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli_module, "DEFAULT_CONFIG_PATH", tmp_path / "config.toml")
    assert _pidfile_path(None) == tmp_path / "cortex.pid"


def test_read_pidfile_missing_returns_none(tmp_path: Path):
    assert _read_pidfile(tmp_path / "nope.pid") is None


def test_read_pidfile_corrupt_returns_none(tmp_path: Path):
    pidfile = tmp_path / "cortex.pid"
    pidfile.write_text("not-a-number", encoding="utf-8")
    assert _read_pidfile(pidfile) is None


def test_read_pidfile_valid(tmp_path: Path):
    pidfile = tmp_path / "cortex.pid"
    pidfile.write_text("12345", encoding="utf-8")
    assert _read_pidfile(pidfile) == 12345


def test_is_process_running_current_process_true():
    assert _is_process_running(os.getpid()) is True


def test_is_process_running_bogus_pid_false():
    assert _is_process_running(999_999_999) is False


# ---------------------------------------------------------------------------
# CLI integration — start --background / stop
# ---------------------------------------------------------------------------


def test_start_background_spawns_and_writes_pidfile(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    monkeypatch.setattr(cli_module, "_spawn_background", lambda cmd: 4242)

    result = runner.invoke(cli, ["-c", str(config_file), "start", "--background"])

    assert result.exit_code == 0
    assert "4242" in result.output
    pidfile = tmp_path / "cortex.pid"
    assert pidfile.read_text(encoding="utf-8").strip() == "4242"


def test_start_background_already_running_is_noop(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    (tmp_path / "cortex.pid").write_text(str(os.getpid()), encoding="utf-8")

    spawn_calls = []
    monkeypatch.setattr(cli_module, "_spawn_background", lambda cmd: spawn_calls.append(cmd) or 0)

    result = runner.invoke(cli, ["-c", str(config_file), "start", "--background"])

    assert result.exit_code == 0
    assert "already running" in result.output
    assert spawn_calls == []


def test_stop_no_pidfile_reports_not_tracked(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "stop"])

    assert result.exit_code == 0
    assert "is tracked" in result.output


def test_stop_stale_pidfile_cleans_up(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    (tmp_path / "cortex.pid").write_text("999999999", encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "stop"])

    assert result.exit_code == 0
    assert "not running" in result.output
    assert not (tmp_path / "cortex.pid").exists()


def test_stop_corrupt_pidfile_removed(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    (tmp_path / "cortex.pid").write_text("garbage", encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "stop"])

    assert result.exit_code == 0
    assert "Corrupt" in result.output
    assert not (tmp_path / "cortex.pid").exists()


def test_stop_running_process_terminates_and_clears_pidfile(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    (tmp_path / "cortex.pid").write_text(str(os.getpid()), encoding="utf-8")

    terminated = []
    monkeypatch.setattr(cli_module, "_terminate_process", lambda pid: terminated.append(pid))

    result = runner.invoke(cli, ["-c", str(config_file), "stop"])

    assert result.exit_code == 0
    assert "Stopped" in result.output
    assert terminated == [os.getpid()]
    assert not (tmp_path / "cortex.pid").exists()
