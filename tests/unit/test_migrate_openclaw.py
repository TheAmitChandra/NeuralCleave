"""Tests for neuralcleave.migrate.openclaw — the OpenClaw config importer."""

from __future__ import annotations

from pathlib import Path

import pytest

from neuralcleave.config import _parse_config
from neuralcleave.migrate.openclaw import (
    migrate,
    migrate_file,
    parse_dotenv,
    parse_openclaw_config,
)

# ---------------------------------------------------------------------------
# parse_openclaw_config — JSON5 tolerance
# ---------------------------------------------------------------------------


class TestParseOpenclawConfig:
    def test_parses_strict_json(self) -> None:
        result = parse_openclaw_config('{"agents": {"defaults": {}}}')
        assert result == {"agents": {"defaults": {}}}

    def test_strips_line_comments(self) -> None:
        result = parse_openclaw_config('{\n  // a comment\n  "a": 1\n}')
        assert result == {"a": 1}

    def test_quotes_unquoted_keys(self) -> None:
        """The style every OpenClaw doc example uses: agents: {...}, not "agents": {...}."""
        result = parse_openclaw_config("{ agents: { defaults: {} } }")
        assert result == {"agents": {"defaults": {}}}

    def test_strips_trailing_commas(self) -> None:
        result = parse_openclaw_config('{"a": 1, "b": 2,}')
        assert result == {"a": 1, "b": 2}

    def test_handles_all_three_json5_features_together(self) -> None:
        text = """
        {
          // top-level comment
          channels: {
            telegram: {
              enabled: true,
              botToken: "abc123",
            },
          },
        }
        """
        result = parse_openclaw_config(text)
        assert result == {"channels": {"telegram": {"enabled": True, "botToken": "abc123"}}}


# ---------------------------------------------------------------------------
# parse_dotenv
# ---------------------------------------------------------------------------


class TestParseDotenv:
    def test_parses_key_value_pairs(self) -> None:
        result = parse_dotenv("ANTHROPIC_API_KEY=sk-ant-123\nOPENAI_API_KEY=sk-abc")
        assert result == {"ANTHROPIC_API_KEY": "sk-ant-123", "OPENAI_API_KEY": "sk-abc"}

    def test_ignores_comments_and_blank_lines(self) -> None:
        text = "# a comment\n\nANTHROPIC_API_KEY=sk-ant-123\n\n# another\n"
        result = parse_dotenv(text)
        assert result == {"ANTHROPIC_API_KEY": "sk-ant-123"}

    def test_strips_quotes_from_values(self) -> None:
        result = parse_dotenv('KEY1="quoted"\nKEY2=\'single\'')
        assert result == {"KEY1": "quoted", "KEY2": "single"}

    def test_empty_text_returns_empty_dict(self) -> None:
        assert parse_dotenv("") == {}


# ---------------------------------------------------------------------------
# migrate — provider API keys
# ---------------------------------------------------------------------------


class TestMigrateProviders:
    def test_migrates_known_provider_key(self) -> None:
        cfg = {"env": {"vars": {"ANTHROPIC_API_KEY": "sk-ant-x"}}}
        result = migrate(cfg)
        assert "ANTHROPIC_API_KEY" in result.migrated_providers
        assert 'anthropic_api_key = "ENV:ANTHROPIC_API_KEY"' in result.toml_text

    def test_skips_unknown_provider_key(self) -> None:
        """GROQ_API_KEY: NeuralCleave has no Groq provider — must not be guessed at."""
        cfg = {"env": {"vars": {"GROQ_API_KEY": "gsk-x"}}}
        result = migrate(cfg)
        assert result.migrated_providers == []
        assert "GROQ" not in result.toml_text

    def test_migrates_multiple_provider_keys(self) -> None:
        cfg = {"env": {"vars": {"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "b", "OPENROUTER_API_KEY": "c"}}}
        result = migrate(cfg)
        assert set(result.migrated_providers) == {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"}

    def test_no_env_vars_produces_no_models_section(self) -> None:
        result = migrate({})
        assert "[models]" not in result.toml_text

    def test_extra_env_vars_override_and_merge_with_json_vars(self) -> None:
        """Matches OpenClaw's own documented precedence: .env overrides openclaw.json's env.vars."""
        cfg = {"env": {"vars": {"ANTHROPIC_API_KEY": "from-json"}}}
        result = migrate(cfg, env_vars={"OPENAI_API_KEY": "from-dotenv"})
        assert set(result.migrated_providers) == {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"}


# ---------------------------------------------------------------------------
# migrate — primary model
# ---------------------------------------------------------------------------


class TestMigratePrimaryModel:
    def test_maps_known_provider_prefix(self) -> None:
        cfg = {"agents": {"defaults": {"model": {"primary": "anthropic/claude-sonnet-4-6"}}}}
        result = migrate(cfg)
        assert result.primary_model == "claude-opus-4-8"
        assert 'primary = "claude-opus-4-8"' in result.toml_text

    def test_unknown_provider_prefix_is_not_mapped(self) -> None:
        cfg = {"agents": {"defaults": {"model": {"primary": "unknown-vendor/some-model"}}}}
        result = migrate(cfg)
        assert result.primary_model is None

    def test_missing_primary_model_is_none(self) -> None:
        result = migrate({})
        assert result.primary_model is None

    def test_non_slash_primary_model_is_ignored(self) -> None:
        cfg = {"agents": {"defaults": {"model": {"primary": "just-a-name"}}}}
        result = migrate(cfg)
        assert result.primary_model is None


# ---------------------------------------------------------------------------
# migrate — channels
# ---------------------------------------------------------------------------


class TestMigrateChannels:
    def test_migrates_telegram_bot_token(self) -> None:
        cfg = {"channels": {"telegram": {"enabled": True, "botToken": "tg-token"}}}
        result = migrate(cfg)
        assert "telegram" in result.migrated_channels
        assert 'bot_token = "tg-token"' in result.toml_text

    def test_migrates_discord_token_field_name(self) -> None:
        """Discord's OpenClaw field is "token", not "botToken" — different from telegram/slack."""
        cfg = {"channels": {"discord": {"enabled": True, "token": "discord-token"}}}
        result = migrate(cfg)
        assert "discord" in result.migrated_channels
        assert 'bot_token = "discord-token"' in result.toml_text

    def test_migrates_slack_bot_token(self) -> None:
        cfg = {"channels": {"slack": {"enabled": True, "botToken": "xoxb-x"}}}
        result = migrate(cfg)
        assert "slack" in result.migrated_channels

    def test_unsupported_channel_is_skipped(self) -> None:
        cfg = {"channels": {"whatsapp": {"allowFrom": ["+1"]}}}
        result = migrate(cfg)
        assert result.migrated_channels == []
        assert result.skipped_channels == ["whatsapp"]

    def test_supported_channel_without_token_is_skipped(self) -> None:
        """Token only in a channel-specific env fallback (not handled) — report, don't guess."""
        cfg = {"channels": {"telegram": {"enabled": True}}}
        result = migrate(cfg)
        assert result.migrated_channels == []
        assert result.skipped_channels == ["telegram"]

    def test_no_channels_produces_empty_lists(self) -> None:
        result = migrate({})
        assert result.migrated_channels == []
        assert result.skipped_channels == []

    def test_mixed_supported_and_unsupported_channels(self) -> None:
        cfg = {
            "channels": {
                "telegram": {"botToken": "t"},
                "whatsapp": {"allowFrom": ["+1"]},
                "signal": {"phoneNumber": "+1"},
            }
        }
        result = migrate(cfg)
        assert result.migrated_channels == ["telegram"]
        assert set(result.skipped_channels) == {"whatsapp", "signal"}


# ---------------------------------------------------------------------------
# migrate — output is valid, round-trippable TOML
# ---------------------------------------------------------------------------


class TestOutputRoundTrips:
    def test_output_parses_as_valid_toml(self) -> None:
        cfg = {
            "env": {"vars": {"ANTHROPIC_API_KEY": "a"}},
            "channels": {"telegram": {"botToken": "t"}},
        }
        result = migrate(cfg)
        import tomllib

        parsed = tomllib.loads(result.toml_text)
        assert parsed["models"]["anthropic_api_key"] == "ENV:ANTHROPIC_API_KEY"
        assert parsed["channels"]["telegram"]["bot_token"] == "t"

    def test_output_loads_through_neuralcleave_parse_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_parse_config resolves ENV:VAR immediately, so prove the full chain — TOML
        text -> parsed dict -> resolved NeuralCleave config -> a usable value."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "resolved-at-runtime")
        cfg = {
            "env": {"vars": {"ANTHROPIC_API_KEY": "a"}},
            "channels": {"telegram": {"botToken": "t"}},
        }
        result = migrate(cfg)
        import tomllib

        nc_cfg = _parse_config(tomllib.loads(result.toml_text))
        assert nc_cfg.models.anthropic_api_key == "resolved-at-runtime"
        assert nc_cfg.channels["telegram"].get("bot_token") == "t"
        assert nc_cfg.channels["telegram"].enabled is True

    def test_always_includes_agent_section(self) -> None:
        result = migrate({})
        assert "[agent]" in result.toml_text
        assert 'name = "My Assistant"' in result.toml_text


# ---------------------------------------------------------------------------
# migrate_file — file I/O + sibling .env auto-detection
# ---------------------------------------------------------------------------


class TestMigrateFile:
    def test_reads_and_migrates_config_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "openclaw.json"
        config_path.write_text('{"env": {"vars": {"ANTHROPIC_API_KEY": "sk-ant"}}}', encoding="utf-8")

        result = migrate_file(config_path)

        assert "ANTHROPIC_API_KEY" in result.migrated_providers

    def test_auto_detects_sibling_dotenv(self, tmp_path: Path) -> None:
        config_path = tmp_path / "openclaw.json"
        config_path.write_text("{}", encoding="utf-8")
        (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-env\n", encoding="utf-8")

        result = migrate_file(config_path)

        assert "OPENAI_API_KEY" in result.migrated_providers

    def test_no_sibling_dotenv_does_not_raise(self, tmp_path: Path) -> None:
        config_path = tmp_path / "openclaw.json"
        config_path.write_text("{}", encoding="utf-8")

        result = migrate_file(config_path)

        assert result.migrated_providers == []

    def test_explicit_env_path_overrides_sibling_autodetect(self, tmp_path: Path) -> None:
        config_path = tmp_path / "openclaw.json"
        config_path.write_text("{}", encoding="utf-8")
        (tmp_path / ".env").write_text("OPENAI_API_KEY=sibling\n", encoding="utf-8")
        explicit_env = tmp_path / "custom.env"
        explicit_env.write_text("ANTHROPIC_API_KEY=explicit\n", encoding="utf-8")

        result = migrate_file(config_path, env_path=explicit_env)

        assert "ANTHROPIC_API_KEY" in result.migrated_providers
        assert "OPENAI_API_KEY" not in result.migrated_providers

    def test_missing_config_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            migrate_file(tmp_path / "does-not-exist.json")

    def test_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "openclaw.json"
        config_path.write_text("{not valid at all", encoding="utf-8")
        with pytest.raises(ValueError):
            migrate_file(config_path)
