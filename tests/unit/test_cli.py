"""Unit tests for cortexflow.cli — status, channels add/remove, memory clear, config edit."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from click.testing import CliRunner

from cortexflow.cli import _channel_detail, _channel_status, _set_channel_enabled, cli
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
