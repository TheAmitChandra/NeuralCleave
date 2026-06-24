"""Unit tests for cortexflow.cli — status, channels add/remove, memory clear, config edit."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

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
# memory edit
# ---------------------------------------------------------------------------


def _seed_single_entry(db_path: Path, content: str = "original text", importance: float = 0.5) -> None:
    from cortexflow.memory.long_term import LongTermMemory

    async def _seed() -> None:
        lt = LongTermMemory(db_path=str(db_path))
        await lt.init_schema()
        await lt.store("s1", content, importance)

    asyncio.run(_seed())


def test_memory_edit_no_flags_errors(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")
    _seed_single_entry(db_path)

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "edit", "1"])

    assert result.exit_code != 0
    assert "Provide --content and/or --importance" in result.output


def test_memory_edit_content(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")
    _seed_single_entry(db_path)

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "edit", "1", "--content", "new text"])

    assert result.exit_code == 0
    assert "Updated memory entry 1" in result.output

    from cortexflow.memory.long_term import LongTermMemory

    async def _check() -> None:
        lt = LongTermMemory(db_path=str(db_path))
        rows = await lt.get_by_session("s1")
        assert rows[0]["content"] == "new text"

    asyncio.run(_check())


def test_memory_edit_importance(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")
    _seed_single_entry(db_path, importance=0.2)

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "edit", "1", "--importance", "0.95"])

    assert result.exit_code == 0

    from cortexflow.memory.long_term import LongTermMemory

    async def _check() -> None:
        lt = LongTermMemory(db_path=str(db_path))
        rows = await lt.get_by_session("s1")
        assert rows[0]["importance_score"] == pytest.approx(0.95)

    asyncio.run(_check())


def test_memory_edit_missing_id_reports_not_found(tmp_path: Path, runner: CliRunner):
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")
    _seed_single_entry(db_path)

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "edit", "99999", "--content", "x"])

    assert result.exit_code == 0
    assert "No memory entry found" in result.output


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
# memory archive
# ---------------------------------------------------------------------------


def _patch_router_generate(monkeypatch: pytest.MonkeyPatch, summary: str = "Archived summary text.") -> None:
    from cortexflow.models.router import ModelRouter

    class _FakeResult:
        def __init__(self, text: str) -> None:
            self.text = text

    async def _fake_generate(self, prompt, **kwargs):  # noqa: ANN001
        return _FakeResult(summary)

    monkeypatch.setattr(ModelRouter, "generate", _fake_generate)


def test_memory_archive_no_stale_sessions(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    _patch_router_generate(monkeypatch)
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "archive"])

    assert result.exit_code == 0
    assert "No sessions inactive" in result.output


def test_memory_archive_missing_session_reports_nothing(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    _patch_router_generate(monkeypatch)
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "archive", "--session", "ghost"])

    assert result.exit_code == 0
    assert "Nothing to archive" in result.output


def test_memory_archive_specific_session(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    _patch_router_generate(monkeypatch, summary="Condensed summary text.")
    config_file = tmp_path / "config.toml"
    db_path = tmp_path / "memory.db"
    config_file.write_text(f'[memory]\nsqlite_path = "{db_path.as_posix()}"\n', encoding="utf-8")
    _seed_memory(db_path)

    result = runner.invoke(cli, ["-c", str(config_file), "memory", "archive", "--session", "session-A"])

    assert result.exit_code == 0
    assert "Archived session" in result.output

    from cortexflow.memory.long_term import LongTermMemory

    async def _check() -> None:
        lt = LongTermMemory(db_path=str(db_path))
        rows = await lt.get_by_session("session-A")
        assert len(rows) == 1
        assert rows[0]["memory_type"] == "archive_summary"

    asyncio.run(_check())


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


def test_start_background_forwards_bind_and_port(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    spawn_calls = []
    monkeypatch.setattr(cli_module, "_spawn_background", lambda cmd: spawn_calls.append(cmd) or 1)

    result = runner.invoke(
        cli, ["-c", str(config_file), "start", "--background", "--bind", "0.0.0.0", "--port", "9999"]
    )

    assert result.exit_code == 0
    assert spawn_calls
    cmd = spawn_calls[0]
    assert "--bind" in cmd
    assert cmd[cmd.index("--bind") + 1] == "0.0.0.0"
    assert "--port" in cmd
    assert cmd[cmd.index("--port") + 1] == "9999"


def test_start_foreground_applies_bind_and_port_override(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[gateway]\nbind = "127.0.0.1"\nport = 7432\n', encoding="utf-8")

    seen_cfg = {}

    def fake_run(cfg):
        seen_cfg["bind"] = cfg.gateway.bind
        seen_cfg["port"] = cfg.gateway.port

    monkeypatch.setattr("cortexflow.gateway.main.run", fake_run)

    result = runner.invoke(cli, ["-c", str(config_file), "start", "--bind", "0.0.0.0", "--port", "9999"])

    assert result.exit_code == 0
    assert seen_cfg == {"bind": "0.0.0.0", "port": 9999}


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


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def _patch_latest_version(monkeypatch: pytest.MonkeyPatch, version: str | None) -> None:
    import cortexflow.update_checker as update_checker_module

    async def _fake_get_latest_version(package, timeout=5.0):  # noqa: ANN001
        return version

    monkeypatch.setattr(update_checker_module, "get_latest_version", _fake_get_latest_version)


def test_update_check_failure_reports_friendly_message(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    _patch_latest_version(monkeypatch, None)

    result = runner.invoke(cli, ["update"])

    assert result.exit_code == 0
    assert "Could not check for updates" in result.output


def test_update_already_up_to_date(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    from cortexflow import __version__

    _patch_latest_version(monkeypatch, __version__)

    result = runner.invoke(cli, ["update"])

    assert result.exit_code == 0
    assert "up to date" in result.output


def test_update_check_flag_does_not_install(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    _patch_latest_version(monkeypatch, "99.0.0")
    install_calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: install_calls.append((a, k)) or MagicMock(returncode=0, stderr=""),
    )

    result = runner.invoke(cli, ["update", "--check"])

    assert result.exit_code == 0
    assert "Update available" in result.output
    assert install_calls == []


def test_update_installs_when_newer_available(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    _patch_latest_version(monkeypatch, "99.0.0")
    fake_result = MagicMock(returncode=0, stderr="")
    install_calls = []

    def _fake_run(*args, **kwargs):
        install_calls.append((args, kwargs))
        return fake_result

    monkeypatch.setattr("subprocess.run", _fake_run)

    result = runner.invoke(cli, ["update"])

    assert result.exit_code == 0
    assert "Updated to v99.0.0" in result.output
    assert len(install_calls) == 1


def test_update_reports_failure_when_pip_fails(runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    _patch_latest_version(monkeypatch, "99.0.0")
    fake_result = MagicMock(returncode=1, stderr="permission denied")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: fake_result)

    result = runner.invoke(cli, ["update"])

    assert result.exit_code == 0
    assert "Update failed" in result.output
    assert "permission denied" in result.output


# ---------------------------------------------------------------------------
# voice clone
# ---------------------------------------------------------------------------


def _patch_clone_voice(monkeypatch: pytest.MonkeyPatch, voice_id: str = "cloned-id-123"):
    from cortexflow.voice.tts import TTSEngine

    calls = []

    async def _fake_clone_voice(self, name, audio_samples, *, description=None):
        calls.append((name, audio_samples, description))
        return voice_id

    monkeypatch.setattr(TTSEngine, "clone_voice", _fake_clone_voice)
    return calls


def test_voice_clone_success(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    calls = _patch_clone_voice(monkeypatch, voice_id="abc123")
    config_file = tmp_path / "config.toml"
    config_file.write_text('[voice]\nelevenlabs_api_key = "sk-test"\n', encoding="utf-8")
    sample_file = tmp_path / "sample.mp3"
    sample_file.write_bytes(b"fake-audio-bytes")

    result = runner.invoke(cli, ["-c", str(config_file), "voice", "clone", "MyVoice", str(sample_file)])

    assert result.exit_code == 0
    assert "abc123" in result.output
    assert len(calls) == 1
    name, samples, description = calls[0]
    assert name == "MyVoice"
    assert samples == [b"fake-audio-bytes"]
    assert description is None


def test_voice_clone_multiple_files(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    calls = _patch_clone_voice(monkeypatch)
    config_file = tmp_path / "config.toml"
    config_file.write_text('[voice]\nelevenlabs_api_key = "sk-test"\n', encoding="utf-8")
    sample1 = tmp_path / "s1.mp3"
    sample2 = tmp_path / "s2.mp3"
    sample1.write_bytes(b"audio-one")
    sample2.write_bytes(b"audio-two")

    result = runner.invoke(
        cli, ["-c", str(config_file), "voice", "clone", "MyVoice", str(sample1), str(sample2)]
    )

    assert result.exit_code == 0
    _, samples, _ = calls[0]
    assert samples == [b"audio-one", b"audio-two"]


def test_voice_clone_with_description(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    calls = _patch_clone_voice(monkeypatch)
    config_file = tmp_path / "config.toml"
    config_file.write_text('[voice]\nelevenlabs_api_key = "sk-test"\n', encoding="utf-8")
    sample_file = tmp_path / "sample.mp3"
    sample_file.write_bytes(b"audio")

    result = runner.invoke(
        cli,
        ["-c", str(config_file), "voice", "clone", "MyVoice", str(sample_file), "-d", "a test voice"],
    )

    assert result.exit_code == 0
    _, _, description = calls[0]
    assert description == "a test voice"


def test_voice_clone_missing_file_errors(tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch):
    _patch_clone_voice(monkeypatch)
    config_file = tmp_path / "config.toml"
    config_file.write_text('[voice]\nelevenlabs_api_key = "sk-test"\n', encoding="utf-8")
    missing_file = tmp_path / "does_not_exist.mp3"

    result = runner.invoke(cli, ["-c", str(config_file), "voice", "clone", "MyVoice", str(missing_file)])

    assert result.exit_code != 0
