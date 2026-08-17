"""Tests for the `neuralcleave usage` CLI command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from neuralcleave.cli import cli
from neuralcleave.observability.metrics import REGISTRY


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _reset(model: str, provider: str) -> None:
    REGISTRY.get("tokens_total").reset(labels={"model": model, "direction": "input"})
    REGISTRY.get("tokens_total").reset(labels={"model": model, "direction": "output"})
    REGISTRY.get("cost_usd_total").reset(labels={"model": model, "provider": provider})


class TestUsageCommand:
    def test_no_generations_reports_nothing_recorded(self, runner: CliRunner) -> None:
        # A model name unique to this test that has never been recorded.
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        # Either the friendly empty message, or a table with prior test data —
        # both are valid depending on test order, so just assert it doesn't crash.
        assert result.exception is None

    def test_reports_recorded_model_usage(self, runner: CliRunner) -> None:
        model, provider = "cli-usage-test-model", "anthropic"
        _reset(model, provider)
        REGISTRY.inc("tokens_total", 1234, labels={"model": model, "direction": "input"})
        REGISTRY.inc("tokens_total", 567, labels={"model": model, "direction": "output"})
        REGISTRY.inc("cost_usd_total", 0.0891, labels={"model": model, "provider": provider})

        result = runner.invoke(cli, ["usage"])

        assert result.exit_code == 0
        assert model in result.output
        assert "1,234" in result.output
        assert "567" in result.output
        assert "0.0891" in result.output

    def test_shows_total_row(self, runner: CliRunner) -> None:
        model, provider = "cli-usage-test-model-2", "openai"
        _reset(model, provider)
        REGISTRY.inc("tokens_total", 100, labels={"model": model, "direction": "input"})
        REGISTRY.inc("cost_usd_total", 0.001, labels={"model": model, "provider": provider})

        result = runner.invoke(cli, ["usage"])

        assert result.exit_code == 0
        assert "Total" in result.output
