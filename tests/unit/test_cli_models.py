"""Tests for the `neuralcleave models` CLI command group."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

import neuralcleave.models.health as health_module
from neuralcleave.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    return cfg


def _mock_async_client(status_code: int = 200):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        return_value=httpx.Response(status_code, json={}, request=httpx.Request("GET", "http://x"))
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch.object(health_module.httpx, "AsyncClient", MagicMock(return_value=mock_client))


class TestModelsList:
    def test_lists_all_providers(self, runner: CliRunner, config_file: Path) -> None:
        result = runner.invoke(cli, ["-c", str(config_file), "models", "list"])
        assert result.exit_code == 0
        assert "anthropic" in result.output
        assert "ollama" in result.output

    def test_shows_configured_provider(self, runner: CliRunner, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[models]\nanthropic_api_key = "sk-configured-test"\n', encoding="utf-8"
        )
        result = runner.invoke(cli, ["-c", str(cfg), "models", "list"])
        assert result.exit_code == 0
        assert "anthropic" in result.output


class TestModelsStatus:
    def test_status_without_live_makes_no_network_call(self, runner: CliRunner, config_file: Path) -> None:
        with patch.object(health_module.httpx, "AsyncClient") as mock_client_cls:
            result = runner.invoke(cli, ["-c", str(config_file), "models", "status"])
        assert result.exit_code == 0
        mock_client_cls.assert_not_called()

    def test_status_live_shows_reachable_column(self, runner: CliRunner, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('[models]\nopenai_api_key = "sk-test"\n', encoding="utf-8")

        with _mock_async_client(200):
            result = runner.invoke(cli, ["-c", str(cfg), "models", "status", "--live"])

        assert result.exit_code == 0
        assert "Reachable" in result.output

    def test_status_live_unreachable_provider_shows_no_and_detail(self, runner: CliRunner, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('[models]\nopenai_api_key = "sk-bad"\n', encoding="utf-8")

        with _mock_async_client(401):
            result = runner.invoke(cli, ["-c", str(cfg), "models", "status", "--live"])

        assert result.exit_code == 0
        assert "rejected" in result.output.lower()

    def test_status_live_title_indicates_live(self, runner: CliRunner, config_file: Path) -> None:
        with _mock_async_client(200):
            result = runner.invoke(cli, ["-c", str(config_file), "models", "status", "--live"])
        assert "(live)" in result.output
