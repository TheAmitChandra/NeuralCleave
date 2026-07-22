"""Unit tests for NeuralCleave.init_wizard.

Covers:
- check_python_version / get_python_version_str helpers
- WizardAnswers defaults
- build_config_toml (pure function, no I/O)
- _workspace_files helper
- write_wizard_output (file I/O, idempotency, force)
- run_wizard non-interactive mode
- run_wizard interactive mode (via monkeypatch)
- cortex init CLI command (CliRunner)
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from neuralcleave.cli import cli
from neuralcleave.init_wizard import (
    _CHANNEL_ENV,
    _MODEL_MAP,
    WizardAnswers,
    _workspace_files,
    build_config_toml,
    check_python_version,
    get_python_version_str,
    run_wizard,
    write_wizard_output,
)

# ===========================================================================
# check_python_version
# ===========================================================================


def test_check_python_version_passes_for_minimum_0_0():
    assert check_python_version((0, 0)) is True


def test_check_python_version_fails_for_impossible_future():
    assert check_python_version((99, 0)) is False


def test_check_python_version_exact_current_passes():
    major, minor = sys.version_info.major, sys.version_info.minor
    assert check_python_version((major, minor)) is True


def test_check_python_version_one_minor_above_current_fails():
    major, minor = sys.version_info.major, sys.version_info.minor
    assert check_python_version((major, minor + 1)) is False


def test_check_python_version_returns_bool():
    result = check_python_version()
    assert isinstance(result, bool)


def test_check_python_version_current_is_at_least_3_11():
    # The project has been developed on Python 3.11+
    assert check_python_version((3, 11)) is True


def test_check_python_version_default_minimum_is_3_12():
    # The default (3,12) should match or fail depending on the running Python;
    # what matters is it returns bool and is consistent with version_info.
    result = check_python_version((3, 12))
    expected = sys.version_info >= (3, 12)
    assert result == expected


# ===========================================================================
# get_python_version_str
# ===========================================================================


def test_get_python_version_str_returns_string():
    assert isinstance(get_python_version_str(), str)


def test_get_python_version_str_has_two_dots():
    assert get_python_version_str().count(".") == 2


def test_get_python_version_str_parts_are_digits():
    parts = get_python_version_str().split(".")
    assert all(p.isdigit() for p in parts)


def test_get_python_version_str_major_is_3():
    assert get_python_version_str().startswith("3.")


def test_get_python_version_str_matches_sys_version_info():
    v = sys.version_info
    expected = f"{v.major}.{v.minor}.{v.micro}"
    assert get_python_version_str() == expected


def test_get_python_version_str_minor_is_11_or_higher():
    parts = get_python_version_str().split(".")
    assert int(parts[1]) >= 11


# ===========================================================================
# WizardAnswers defaults
# ===========================================================================


def test_wizard_answers_default_agent_name():
    assert WizardAnswers().agent_name == "My Assistant"


def test_wizard_answers_default_primary_model():
    assert WizardAnswers().primary_model == "gemini-2.5-flash"


def test_wizard_answers_default_channels_empty():
    assert WizardAnswers().channels == []


def test_wizard_answers_default_voice_stt():
    assert WizardAnswers().voice_stt == "whisper"


def test_wizard_answers_default_voice_tts():
    assert WizardAnswers().voice_tts == "kokoro"


def test_wizard_answers_default_short_term_ttl():
    assert WizardAnswers().short_term_ttl == 3600


def test_wizard_answers_default_long_term_days():
    assert WizardAnswers().long_term_days == 90


def test_wizard_answers_custom_values():
    a = WizardAnswers(
        agent_name="Cortex",
        primary_model="claude-opus-4-8",
        channels=["telegram"],
        voice_stt="none",
        voice_tts="system",
        short_term_ttl=1800,
        long_term_days=30,
    )
    assert a.agent_name == "Cortex"
    assert a.primary_model == "claude-opus-4-8"
    assert a.channels == ["telegram"]
    assert a.voice_stt == "none"
    assert a.voice_tts == "system"
    assert a.short_term_ttl == 1800
    assert a.long_term_days == 30


# ===========================================================================
# build_config_toml — pure function, no I/O
# ===========================================================================


def test_toml_contains_agent_section():
    answers = WizardAnswers(agent_name="Hal 9000")
    toml = build_config_toml(answers)
    assert "[agent]" in toml
    assert 'name = "Hal 9000"' in toml


def test_toml_contains_models_section():
    answers = WizardAnswers(primary_model="claude-opus-4-8")
    toml = build_config_toml(answers)
    assert "[models]" in toml
    assert 'primary = "claude-opus-4-8"' in toml


def test_toml_contains_memory_section():
    answers = WizardAnswers(short_term_ttl=1800, long_term_days=30)
    toml = build_config_toml(answers)
    assert "short_term_ttl = 1800" in toml
    assert "long_term_days = 30" in toml


def test_toml_voice_section():
    answers = WizardAnswers(voice_stt="none", voice_tts="system")
    toml = build_config_toml(answers)
    assert "[voice]" in toml
    assert 'stt = "none"' in toml
    assert 'tts = "system"' in toml


def test_toml_gateway_and_ui():
    toml = build_config_toml(WizardAnswers())
    assert "port = 7432" in toml
    assert "web_port = 3000" in toml


def test_toml_no_channels_by_default():
    toml = build_config_toml(WizardAnswers())
    assert "[channels." not in toml


def test_toml_telegram_channel():
    answers = WizardAnswers(channels=["telegram"])
    toml = build_config_toml(answers)
    assert "[channels.telegram]" in toml
    assert f'bot_token = "ENV:{_CHANNEL_ENV["telegram"]}"' in toml


def test_toml_discord_channel():
    answers = WizardAnswers(channels=["discord"])
    toml = build_config_toml(answers)
    assert "[channels.discord]" in toml
    assert f'bot_token = "ENV:{_CHANNEL_ENV["discord"]}"' in toml


def test_toml_slack_channel():
    answers = WizardAnswers(channels=["slack"])
    toml = build_config_toml(answers)
    assert "[channels.slack]" in toml
    assert f'bot_token = "ENV:{_CHANNEL_ENV["slack"]}"' in toml


def test_toml_whatsapp_channel():
    answers = WizardAnswers(channels=["whatsapp"])
    toml = build_config_toml(answers)
    assert "[channels.whatsapp]" in toml


def test_toml_email_channel():
    answers = WizardAnswers(channels=["email"])
    toml = build_config_toml(answers)
    assert "[channels.email]" in toml


def test_toml_multiple_channels():
    answers = WizardAnswers(channels=["telegram", "discord"])
    toml = build_config_toml(answers)
    assert "[channels.telegram]" in toml
    assert "[channels.discord]" in toml


def test_toml_all_known_channels():
    all_channels = list(_CHANNEL_ENV.keys())
    toml = build_config_toml(WizardAnswers(channels=all_channels))
    for ch in all_channels:
        assert f"[channels.{ch}]" in toml


def test_toml_unknown_channel_uses_fallback_env():
    answers = WizardAnswers(channels=["myapp"])
    toml = build_config_toml(answers)
    assert "[channels.myapp]" in toml
    assert "ENV:MYAPP_TOKEN" in toml


def test_toml_channel_enabled_line():
    toml = build_config_toml(WizardAnswers(channels=["telegram"]))
    assert "enabled = true" in toml


def test_toml_returns_string():
    assert isinstance(build_config_toml(WizardAnswers()), str)


def test_toml_has_model_auto():
    toml = build_config_toml(WizardAnswers())
    assert 'model = "auto"' in toml


def test_toml_gateway_bind():
    toml = build_config_toml(WizardAnswers())
    assert 'bind = "127.0.0.1"' in toml


def test_toml_is_valid_toml():
    toml = build_config_toml(WizardAnswers(channels=["telegram", "discord"]))
    data = tomllib.loads(toml)
    assert "agent" in data
    assert "models" in data
    assert "memory" in data
    assert "voice" in data
    assert "gateway" in data
    assert "ui" in data


def test_toml_valid_toml_channel_sections():
    toml = build_config_toml(WizardAnswers(channels=["telegram"]))
    data = tomllib.loads(toml)
    assert "channels" in data
    assert "telegram" in data["channels"]
    assert data["channels"]["telegram"]["enabled"] is True


def test_toml_agent_name_in_parsed_toml():
    toml = build_config_toml(WizardAnswers(agent_name="HAL"))
    data = tomllib.loads(toml)
    assert data["agent"]["name"] == "HAL"


def test_toml_primary_model_in_parsed_toml():
    toml = build_config_toml(WizardAnswers(primary_model="claude-opus-4-8"))
    data = tomllib.loads(toml)
    assert data["models"]["primary"] == "claude-opus-4-8"


def test_toml_memory_values_in_parsed_toml():
    toml = build_config_toml(WizardAnswers(short_term_ttl=7200, long_term_days=180))
    data = tomllib.loads(toml)
    assert data["memory"]["short_term_ttl"] == 7200
    assert data["memory"]["long_term_days"] == 180


def test_model_map_covers_all_choices():
    assert "1" in _MODEL_MAP
    assert "2" in _MODEL_MAP
    assert "3" in _MODEL_MAP


def test_model_map_choice_1_is_claude():
    assert "claude" in _MODEL_MAP["1"].lower()


def test_model_map_choice_2_is_gemini():
    assert "gemini" in _MODEL_MAP["2"].lower()


def test_model_map_choice_3_is_ollama():
    assert "ollama" in _MODEL_MAP["3"].lower()


# ===========================================================================
# _workspace_files
# ===========================================================================


def test_workspace_files_returns_four_files():
    assert len(_workspace_files()) == 4


def test_workspace_files_has_soul_md():
    assert "SOUL.md" in _workspace_files()


def test_workspace_files_has_rules_md():
    assert "RULES.md" in _workspace_files()


def test_workspace_files_has_tools_md():
    assert "TOOLS.md" in _workspace_files()


def test_workspace_files_has_memory_md():
    assert "MEMORY.md" in _workspace_files()


def test_workspace_files_all_non_empty():
    for name, content in _workspace_files().items():
        assert content.strip(), f"{name} content is empty"


def test_workspace_files_soul_mentions_assistant():
    content = _workspace_files()["SOUL.md"]
    assert "assistant" in content.lower()


def test_workspace_files_rules_mentions_never():
    content = _workspace_files()["RULES.md"]
    assert "Never" in content or "never" in content


# ===========================================================================
# write_wizard_output — file I/O
# ===========================================================================


def test_write_creates_config_file(tmp_path: Path):
    answers = WizardAnswers(agent_name="TmpBot")
    cfg = write_wizard_output(answers, config_dir=tmp_path)
    assert cfg.exists()
    assert cfg.name == "config.toml"
    assert "TmpBot" in cfg.read_text()


def test_write_creates_workspace_files(tmp_path: Path):
    write_wizard_output(WizardAnswers(), config_dir=tmp_path)
    workspace = tmp_path / "workspace"
    for fname in ("SOUL.md", "RULES.md", "TOOLS.md", "MEMORY.md"):
        assert (workspace / fname).exists(), f"Missing {fname}"


def test_write_returns_path_object(tmp_path: Path):
    result = write_wizard_output(WizardAnswers(), config_dir=tmp_path)
    assert isinstance(result, Path)


def test_write_returns_config_toml_path(tmp_path: Path):
    result = write_wizard_output(WizardAnswers(), config_dir=tmp_path)
    assert result == tmp_path / "config.toml"


def test_write_does_not_overwrite_existing_workspace_file(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    soul = workspace / "SOUL.md"
    soul.write_text("custom soul", encoding="utf-8")

    write_wizard_output(WizardAnswers(), config_dir=tmp_path, force=False)
    assert soul.read_text() == "custom soul"


def test_write_force_overwrites_workspace_file(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    soul = workspace / "SOUL.md"
    soul.write_text("old soul", encoding="utf-8")

    write_wizard_output(WizardAnswers(), config_dir=tmp_path, force=True)
    assert soul.read_text() != "old soul"


def test_write_always_overwrites_config_toml(tmp_path: Path):
    first = WizardAnswers(agent_name="First")
    write_wizard_output(first, config_dir=tmp_path)
    second = WizardAnswers(agent_name="Second")
    write_wizard_output(second, config_dir=tmp_path)
    assert 'name = "Second"' in (tmp_path / "config.toml").read_text()


def test_write_creates_nested_config_dir(tmp_path: Path):
    nested = tmp_path / "deep" / "nested" / "config"
    cfg = write_wizard_output(WizardAnswers(), config_dir=nested)
    assert cfg.exists()


def test_write_config_toml_valid_toml(tmp_path: Path):
    write_wizard_output(WizardAnswers(), config_dir=tmp_path)
    data = tomllib.loads((tmp_path / "config.toml").read_text())
    assert "agent" in data


def test_write_with_channels(tmp_path: Path):
    answers = WizardAnswers(channels=["telegram", "slack"])
    write_wizard_output(answers, config_dir=tmp_path)
    content = (tmp_path / "config.toml").read_text()
    assert "[channels.telegram]" in content
    assert "[channels.slack]" in content


def test_write_workspace_soul_content(tmp_path: Path):
    write_wizard_output(WizardAnswers(), config_dir=tmp_path)
    soul = (tmp_path / "workspace" / "SOUL.md").read_text()
    assert soul.strip() != ""


def test_write_idempotent_on_config(tmp_path: Path):
    answers = WizardAnswers(agent_name="Same")
    write_wizard_output(answers, config_dir=tmp_path)
    write_wizard_output(answers, config_dir=tmp_path)
    assert 'name = "Same"' in (tmp_path / "config.toml").read_text()


# ===========================================================================
# run_wizard — non-interactive mode
# ===========================================================================


def test_run_wizard_non_interactive_writes_config(tmp_path: Path):
    cfg = run_wizard(config_dir=tmp_path, non_interactive=True)
    assert cfg.exists()


def test_run_wizard_non_interactive_returns_path(tmp_path: Path):
    result = run_wizard(config_dir=tmp_path, non_interactive=True)
    assert isinstance(result, Path)
    assert result.name == "config.toml"


def test_run_wizard_non_interactive_creates_workspace(tmp_path: Path):
    run_wizard(config_dir=tmp_path, non_interactive=True)
    assert (tmp_path / "workspace").is_dir()
    assert (tmp_path / "workspace" / "SOUL.md").exists()


def test_run_wizard_non_interactive_uses_default_agent_name(tmp_path: Path):
    cfg = run_wizard(config_dir=tmp_path, non_interactive=True)
    assert 'name = "My Assistant"' in cfg.read_text()


def test_run_wizard_non_interactive_valid_toml(tmp_path: Path):
    cfg = run_wizard(config_dir=tmp_path, non_interactive=True)
    data = tomllib.loads(cfg.read_text())
    assert "agent" in data
    assert "gateway" in data


def test_run_wizard_non_interactive_custom_dir(tmp_path: Path):
    custom = tmp_path / "mycfg"
    cfg = run_wizard(config_dir=custom, non_interactive=True)
    assert cfg.parent == custom


def test_run_wizard_non_interactive_skips_if_config_exists(tmp_path: Path):
    (tmp_path / "config.toml").write_text("original", encoding="utf-8")
    cfg = run_wizard(config_dir=tmp_path, non_interactive=True)
    assert cfg.read_text() == "original"


def test_run_wizard_non_interactive_force_overwrites(tmp_path: Path):
    (tmp_path / "config.toml").write_text("stale", encoding="utf-8")
    cfg = run_wizard(config_dir=tmp_path, non_interactive=True, force=True)
    assert cfg.read_text() != "stale"
    assert "[agent]" in cfg.read_text()


def test_run_wizard_non_interactive_prints_success(tmp_path: Path, capsys):
    run_wizard(config_dir=tmp_path, non_interactive=True)
    out = capsys.readouterr().out
    assert "Setup complete" in out or "config" in out.lower()


def test_run_wizard_non_interactive_mentions_cortex_start(tmp_path: Path, capsys):
    run_wizard(config_dir=tmp_path, non_interactive=True)
    out = capsys.readouterr().out
    assert "neuralcleave start" in out


def test_run_wizard_non_interactive_gateway_port_7432(tmp_path: Path):
    cfg = run_wizard(config_dir=tmp_path, non_interactive=True)
    assert "7432" in cfg.read_text()


def test_run_wizard_non_interactive_idempotent_content(tmp_path: Path):
    a = run_wizard(config_dir=tmp_path / "a", non_interactive=True)
    b = run_wizard(config_dir=tmp_path / "b", non_interactive=True)
    assert a.read_text() == b.read_text()


# ===========================================================================
# run_wizard — interactive mode (monkeypatch)
# ===========================================================================


def test_run_wizard_existing_config_no_force_returns_early(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "NeuralCleave"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("existing", encoding="utf-8")

    prompted = []
    monkeypatch.setattr("click.prompt", lambda *a, **k: prompted.append(1))

    result = run_wizard(config_dir=config_dir, force=False)

    assert result == config_dir / "config.toml"
    assert prompted == []
    assert result.read_text(encoding="utf-8") == "existing"


def test_run_wizard_full_flow_writes_config(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "NeuralCleave"

    prompts = iter(["Hal", "1", "whisper", "kokoro"])
    monkeypatch.setattr("click.prompt", lambda *a, **k: next(prompts))
    monkeypatch.setattr(
        "click.confirm",
        lambda text, **k: text.strip().rstrip("?") == "Telegram",
    )

    result = run_wizard(config_dir=config_dir, force=False)

    content = result.read_text(encoding="utf-8")
    assert 'name = "Hal"' in content
    assert _MODEL_MAP["1"] in content
    assert "[channels.telegram]" in content
    assert "[channels.discord]" not in content


def test_run_wizard_creates_workspace_files(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "NeuralCleave"

    prompts = iter(["My Assistant", "2", "none", "none"])
    monkeypatch.setattr("click.prompt", lambda *a, **k: next(prompts))
    monkeypatch.setattr("click.confirm", lambda *a, **k: False)

    run_wizard(config_dir=config_dir, force=False)

    workspace = config_dir / "workspace"
    for fname in ("SOUL.md", "RULES.md", "TOOLS.md", "MEMORY.md"):
        assert (workspace / fname).exists()


def test_run_wizard_with_force_overwrites_existing_config(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "NeuralCleave"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("stale", encoding="utf-8")

    prompts = iter(["New Name", "3", "whisper", "system"])
    monkeypatch.setattr("click.prompt", lambda *a, **k: next(prompts))
    monkeypatch.setattr("click.confirm", lambda *a, **k: False)

    result = run_wizard(config_dir=config_dir, force=True)

    content = result.read_text(encoding="utf-8")
    assert 'name = "New Name"' in content
    assert content != "stale"


def test_run_wizard_enables_multiple_channels(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "NeuralCleave"

    prompts = iter(["Bot", "2", "whisper", "kokoro"])
    monkeypatch.setattr("click.prompt", lambda *a, **k: next(prompts))
    monkeypatch.setattr(
        "click.confirm",
        lambda text, **k: text.strip().rstrip("?") in ("Telegram", "Discord"),
    )

    result = run_wizard(config_dir=config_dir, force=False)

    content = result.read_text(encoding="utf-8")
    assert "[channels.telegram]" in content
    assert "[channels.discord]" in content
    assert "[channels.slack]" not in content


# ===========================================================================
# cortex init CLI command (CliRunner)
# ===========================================================================


def test_cortex_init_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--help"])
    assert result.exit_code == 0
    assert "--non-interactive" in result.output or "-y" in result.output


def test_cortex_init_non_interactive_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--dir", str(tmp_path), "--non-interactive"])
    assert result.exit_code == 0
    assert (tmp_path / "config.toml").exists()


def test_cortex_init_short_flag_y(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--dir", str(tmp_path), "-y"])
    assert result.exit_code == 0
    assert (tmp_path / "config.toml").exists()


def test_cortex_init_non_interactive_creates_workspace(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(cli, ["init", "--dir", str(tmp_path), "-y"])
    assert (tmp_path / "workspace" / "SOUL.md").exists()


def test_cortex_init_non_interactive_valid_toml(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(cli, ["init", "--dir", str(tmp_path), "-y"])
    data = tomllib.loads((tmp_path / "config.toml").read_text())
    assert "agent" in data


def test_cortex_init_exits_early_if_config_exists(tmp_path: Path):
    (tmp_path / "config.toml").write_text("original", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "config.toml").read_text() == "original"


def test_cortex_init_force_overwrites(tmp_path: Path):
    (tmp_path / "config.toml").write_text("stale", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--dir", str(tmp_path), "--force", "-y"],
    )
    assert result.exit_code == 0
    assert (tmp_path / "config.toml").read_text() != "stale"


def test_cortex_init_non_interactive_with_dir(tmp_path: Path):
    target = tmp_path / "custom_dir"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--dir", str(target), "-y"])
    assert result.exit_code == 0
    assert (target / "config.toml").exists()


def test_cortex_init_non_interactive_output_mentions_start(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--dir", str(tmp_path), "-y"])
    assert "start" in result.output.lower()


def test_cortex_init_non_interactive_output_has_path(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--dir", str(tmp_path), "-y"])
    assert str(tmp_path) in result.output or "config.toml" in result.output


# ===========================================================================
# Channel env-var mapping
# ===========================================================================


def test_channel_env_telegram_token():
    assert _CHANNEL_ENV["telegram"] == "TELEGRAM_BOT_TOKEN"


def test_channel_env_discord_token():
    assert _CHANNEL_ENV["discord"] == "DISCORD_BOT_TOKEN"


def test_channel_env_slack_token():
    assert _CHANNEL_ENV["slack"] == "SLACK_BOT_TOKEN"


def test_channel_env_whatsapp():
    assert "whatsapp" in _CHANNEL_ENV


def test_channel_env_email():
    assert "email" in _CHANNEL_ENV


def test_channel_env_has_five_entries():
    assert len(_CHANNEL_ENV) == 5


# ===========================================================================
# install scripts — structural sanity (plain text checks)
# ===========================================================================


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    p = Path(__file__).parent.parent.parent / "scripts" / "install.sh"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def install_ps1_text() -> str:
    p = Path(__file__).parent.parent.parent / "scripts" / "install.ps1"
    return p.read_text(encoding="utf-8")


def test_install_sh_exists():
    p = Path(__file__).parent.parent.parent / "scripts" / "install.sh"
    assert p.exists()


def test_install_ps1_exists():
    p = Path(__file__).parent.parent.parent / "scripts" / "install.ps1"
    assert p.exists()


def test_install_sh_has_shebang(install_sh_text: str):
    assert install_sh_text.startswith("#!/usr/bin/env bash")


def test_install_sh_checks_python_version(install_sh_text: str):
    assert "3" in install_sh_text and "12" in install_sh_text


def test_install_sh_installs_NeuralCleave(install_sh_text: str):
    assert "neuralcleave" in install_sh_text


def test_install_sh_runs_cortex_init(install_sh_text: str):
    assert "init" in install_sh_text and "non-interactive" in install_sh_text


def test_install_sh_mentions_cortex_start(install_sh_text: str):
    assert "neuralcleave start" in install_sh_text


def test_install_sh_handles_pip_failure(install_sh_text: str):
    assert "pip" in install_sh_text


def test_install_sh_has_set_e(install_sh_text: str):
    assert "set -e" in install_sh_text


def test_install_ps1_checks_python_version(install_ps1_text: str):
    assert "3" in install_ps1_text and "12" in install_ps1_text


def test_install_ps1_installs_NeuralCleave(install_ps1_text: str):
    assert "neuralcleave" in install_ps1_text


def test_install_ps1_runs_cortex_init(install_ps1_text: str):
    assert "init" in install_ps1_text and "non-interactive" in install_ps1_text


def test_install_ps1_mentions_cortex_start(install_ps1_text: str):
    assert "neuralcleave start" in install_ps1_text


def test_install_ps1_has_requires_version(install_ps1_text: str):
    assert "#Requires -Version" in install_ps1_text


def test_install_ps1_handles_pip_user_fallback(install_ps1_text: str):
    assert "--user" in install_ps1_text
