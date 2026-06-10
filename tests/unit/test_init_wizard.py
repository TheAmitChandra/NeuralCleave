"""Unit tests for cortexflow.init_wizard — WizardAnswers, build_config_toml, write_wizard_output."""

from __future__ import annotations

from pathlib import Path

from cortexflow.init_wizard import (
    _CHANNEL_ENV,
    _MODEL_MAP,
    WizardAnswers,
    build_config_toml,
    write_wizard_output,
)

# ---------------------------------------------------------------------------
# build_config_toml — pure function tests
# ---------------------------------------------------------------------------


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
    assert '[voice]' in toml
    assert 'stt = "none"' in toml
    assert 'tts = "system"' in toml


def test_toml_gateway_and_ui():
    answers = WizardAnswers()
    toml = build_config_toml(answers)
    assert "port = 7432" in toml
    assert "web_port = 3000" in toml


def test_toml_no_channels_by_default():
    answers = WizardAnswers()
    toml = build_config_toml(answers)
    assert "[channels." not in toml


def test_toml_telegram_channel():
    answers = WizardAnswers(channels=["telegram"])
    toml = build_config_toml(answers)
    assert "[channels.telegram]" in toml
    assert f'bot_token = "ENV:{_CHANNEL_ENV["telegram"]}"' in toml


def test_toml_multiple_channels():
    answers = WizardAnswers(channels=["telegram", "discord"])
    toml = build_config_toml(answers)
    assert "[channels.telegram]" in toml
    assert "[channels.discord]" in toml


def test_toml_unknown_channel_uses_fallback_env():
    answers = WizardAnswers(channels=["myapp"])
    toml = build_config_toml(answers)
    assert "[channels.myapp]" in toml
    assert "ENV:MYAPP_TOKEN" in toml


def test_model_map_covers_all_choices():
    assert "1" in _MODEL_MAP  # claude
    assert "2" in _MODEL_MAP  # gemini
    assert "3" in _MODEL_MAP  # ollama


# ---------------------------------------------------------------------------
# write_wizard_output — file I/O tests
# ---------------------------------------------------------------------------


def test_write_creates_config_file(tmp_path: Path):
    answers = WizardAnswers(agent_name="TmpBot")
    cfg = write_wizard_output(answers, config_dir=tmp_path)
    assert cfg.exists()
    assert cfg.name == "config.toml"
    content = cfg.read_text()
    assert "TmpBot" in content


def test_write_creates_workspace_files(tmp_path: Path):
    answers = WizardAnswers()
    write_wizard_output(answers, config_dir=tmp_path)
    workspace = tmp_path / "workspace"
    for fname in ("SOUL.md", "RULES.md", "TOOLS.md", "MEMORY.md"):
        assert (workspace / fname).exists(), f"Missing {fname}"


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


def test_write_creates_nested_config_dir(tmp_path: Path):
    nested = tmp_path / "deep" / "nested" / "config"
    write_wizard_output(WizardAnswers(), config_dir=nested)
    assert (nested / "config.toml").exists()
