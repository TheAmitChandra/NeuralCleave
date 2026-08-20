"""Tests for `neuralcleave plugins install/uninstall/enable/disable`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from neuralcleave.cli import _is_trusted_plugin_source, cli
from neuralcleave.plugins.state import PluginStateStore


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def fresh_state():
    store = PluginStateStore(db_path=None)
    with patch("neuralcleave.plugins.state.STATE_STORE", store):
        yield store


def _mock_subprocess_run(returncode: int = 0, stderr: str = ""):
    return patch(
        "subprocess.run",
        return_value=MagicMock(returncode=returncode, stderr=stderr),
    )


class TestIsTrustedPluginSource:
    def test_bare_package_name_is_trusted(self):
        assert _is_trusted_plugin_source("neuralcleave-github") is True

    def test_package_name_with_version_pin_is_trusted(self):
        assert _is_trusted_plugin_source("some-plugin==1.2.3") is True

    def test_existing_local_path_is_trusted(self, tmp_path):
        assert _is_trusted_plugin_source(str(tmp_path)) is True

    def test_git_url_is_not_trusted(self):
        assert _is_trusted_plugin_source("git+https://github.com/x/y.git") is False

    def test_raw_https_url_is_not_trusted(self):
        assert _is_trusted_plugin_source("https://example.com/plugin.tar.gz") is False


class TestPluginsInstall:
    def test_trusted_source_installs_without_force(self, runner: CliRunner) -> None:
        with _mock_subprocess_run(returncode=0):
            result = runner.invoke(cli, ["plugins", "install", "some-plugin"])
        assert result.exit_code == 0
        assert "Installed" in result.output

    def test_untrusted_source_refused_without_force(self, runner: CliRunner) -> None:
        with patch("subprocess.run") as mock_run:
            result = runner.invoke(cli, ["plugins", "install", "git+https://x/y.git"])
        assert result.exit_code != 0
        mock_run.assert_not_called()

    def test_untrusted_source_installs_with_force(self, runner: CliRunner) -> None:
        with _mock_subprocess_run(returncode=0):
            result = runner.invoke(
                cli, ["plugins", "install", "git+https://x/y.git", "--force"]
            )
        assert result.exit_code == 0

    def test_pip_failure_reports_error(self, runner: CliRunner) -> None:
        with _mock_subprocess_run(returncode=1, stderr="no such package"):
            result = runner.invoke(cli, ["plugins", "install", "some-plugin"])
        assert result.exit_code != 0
        assert "failed" in result.output.lower()


class TestPluginsUninstall:
    def test_aborts_without_yes(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["plugins", "uninstall", "some-plugin"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_uninstalls_with_yes(self, runner: CliRunner) -> None:
        with _mock_subprocess_run(returncode=0):
            result = runner.invoke(cli, ["plugins", "uninstall", "some-plugin", "--yes"])
        assert result.exit_code == 0
        assert "Uninstalled" in result.output

    def test_pip_failure_reports_error(self, runner: CliRunner) -> None:
        with _mock_subprocess_run(returncode=1, stderr="not installed"):
            result = runner.invoke(cli, ["plugins", "uninstall", "some-plugin", "--yes"])
        assert result.exit_code != 0


class TestPluginsEnableDisable:
    def test_disable_persists_in_state_store(self, runner: CliRunner, fresh_state) -> None:
        result = runner.invoke(cli, ["plugins", "disable", "my-plugin"])
        assert result.exit_code == 0
        assert fresh_state.is_enabled("my-plugin") is False

    def test_enable_persists_in_state_store(self, runner: CliRunner, fresh_state) -> None:
        fresh_state.set_enabled("my-plugin", False)
        result = runner.invoke(cli, ["plugins", "enable", "my-plugin"])
        assert result.exit_code == 0
        assert fresh_state.is_enabled("my-plugin") is True
