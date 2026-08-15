"""Tests for the `neuralcleave migrate openclaw` CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from neuralcleave.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _write_openclaw_config(path: Path, body: str) -> Path:
    config_path = path / "openclaw.json"
    config_path.write_text(body, encoding="utf-8")
    return config_path


class TestDryRun:
    def test_prints_toml_with_section_headers_intact(self, tmp_path: Path, runner: CliRunner) -> None:
        """Regression guard: Rich console markup reads "[agent]" as a style tag
        and silently strips it unless markup=False is passed when printing."""
        config_path = _write_openclaw_config(
            tmp_path, '{ env: { vars: { ANTHROPIC_API_KEY: "sk-x" } } }'
        )

        result = runner.invoke(cli, ["migrate", "openclaw", str(config_path), "--dry-run"])

        assert result.exit_code == 0
        assert "[agent]" in result.output
        assert "[models]" in result.output
        assert 'anthropic_api_key = "ENV:ANTHROPIC_API_KEY"' in result.output

    def test_does_not_write_any_file(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(tmp_path, "{}")
        output_path = tmp_path / "config.toml"

        runner.invoke(cli, ["migrate", "openclaw", str(config_path), "--dry-run", "-o", str(output_path)])

        assert not output_path.exists()

    def test_reports_migrated_providers(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(
            tmp_path, '{ env: { vars: { ANTHROPIC_API_KEY: "sk-x" } } }'
        )

        result = runner.invoke(cli, ["migrate", "openclaw", str(config_path), "--dry-run"])

        assert "Migrated provider keys: ANTHROPIC_API_KEY" in result.output

    def test_reports_skipped_channels(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(
            tmp_path, '{ channels: { whatsapp: { allowFrom: ["+1"] } } }'
        )

        result = runner.invoke(cli, ["migrate", "openclaw", str(config_path), "--dry-run"])

        assert "Skipped channels" in result.output
        assert "whatsapp" in result.output

    def test_nothing_recognized_prints_helpful_message(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(tmp_path, "{}")

        result = runner.invoke(cli, ["migrate", "openclaw", str(config_path), "--dry-run"])

        assert "Nothing recognized to migrate" in result.output


class TestWriteToOutput:
    def test_writes_converted_config_to_output_path(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(tmp_path, '{ channels: { discord: { token: "dt" } } }')
        output_path = tmp_path / "converted.toml"

        result = runner.invoke(cli, ["migrate", "openclaw", str(config_path), "-o", str(output_path)])

        assert result.exit_code == 0
        assert output_path.exists()
        assert 'bot_token = "dt"' in output_path.read_text(encoding="utf-8")

    def test_refuses_to_overwrite_existing_output(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(tmp_path, "{}")
        output_path = tmp_path / "converted.toml"
        output_path.write_text("existing content\n", encoding="utf-8")

        result = runner.invoke(cli, ["migrate", "openclaw", str(config_path), "-o", str(output_path)])

        assert result.exit_code != 0
        assert output_path.read_text(encoding="utf-8") == "existing content\n"


class TestEnvFileOption:
    def test_explicit_env_file_is_used(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(tmp_path, "{}")
        env_path = tmp_path / "custom.env"
        env_path.write_text("ANTHROPIC_API_KEY=sk-from-custom-env\n", encoding="utf-8")

        result = runner.invoke(
            cli, ["migrate", "openclaw", str(config_path), "--env-file", str(env_path), "--dry-run"]
        )

        assert "ANTHROPIC_API_KEY" in result.output


class TestErrorHandling:
    def test_missing_config_file_fails_with_nonzero_exit(self, tmp_path: Path, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["migrate", "openclaw", str(tmp_path / "nope.json")])
        assert result.exit_code != 0

    def test_invalid_json_reports_error_and_exits_nonzero(self, tmp_path: Path, runner: CliRunner) -> None:
        config_path = _write_openclaw_config(tmp_path, "{not valid")

        result = runner.invoke(cli, ["migrate", "openclaw", str(config_path)])

        assert result.exit_code != 0
        assert "Could not parse" in result.output
