"""Tests for op:// (1Password CLI) secret resolution in config.resolve_secret()."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from neuralcleave.config import resolve_secret


class TestOnePasswordResolution:
    def test_resolves_op_reference_via_cli(self) -> None:
        mock_result = MagicMock(returncode=0, stdout="sk-ant-resolved\n", stderr="")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = resolve_secret("op://Private/Anthropic/api_key")

        assert result == "sk-ant-resolved"
        mock_run.assert_called_once_with(
            ["op", "read", "op://Private/Anthropic/api_key"],
            capture_output=True, text=True, timeout=10,
        )

    def test_strips_trailing_whitespace_from_op_output(self) -> None:
        mock_result = MagicMock(returncode=0, stdout="  value-with-spaces  \n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = resolve_secret("op://vault/item/field")
        assert result == "value-with-spaces"

    def test_op_cli_not_installed_raises_runtime_error(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(RuntimeError, match="1Password CLI"):
                resolve_secret("op://vault/item/field")

    def test_op_cli_not_installed_error_mentions_install_url(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(RuntimeError, match="developer.1password.com"):
                resolve_secret("op://vault/item/field")

    def test_op_cli_nonzero_exit_raises_with_stderr(self) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="[ERROR] item not found")
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="item not found"):
                resolve_secret("op://vault/missing-item/field")

    def test_op_cli_timeout_raises_runtime_error(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="op", timeout=10)):
            with pytest.raises(RuntimeError, match="timed out"):
                resolve_secret("op://vault/item/field")

    def test_op_cli_timeout_error_mentions_signin(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="op", timeout=10)):
            with pytest.raises(RuntimeError, match="op signin"):
                resolve_secret("op://vault/item/field")

    def test_does_not_call_op_for_env_reference(self) -> None:
        with patch("subprocess.run") as mock_run:
            resolve_secret("ENV:SOME_VAR")
        mock_run.assert_not_called()

    def test_does_not_call_op_for_plain_value(self) -> None:
        with patch("subprocess.run") as mock_run:
            resolve_secret("just-a-plain-string")
        mock_run.assert_not_called()


class TestExistingBehaviorUnchanged:
    """Regression guard: the op:// addition must not change ENV:/plain-value behavior."""

    def test_env_reference_still_resolves(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_TEST_VAR", "resolved-value")
        assert resolve_secret("ENV:MY_TEST_VAR") == "resolved-value"

    def test_missing_env_var_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DOES_NOT_EXIST_VAR", raising=False)
        assert resolve_secret("ENV:DOES_NOT_EXIST_VAR") == ""

    def test_plain_value_returned_unchanged(self) -> None:
        assert resolve_secret("plain-api-key-value") == "plain-api-key-value"

    def test_empty_string_returns_empty_string(self) -> None:
        assert resolve_secret("") == ""

    def test_none_normalizes_to_empty_string(self) -> None:
        """Some of the 19 channel _resolve duplicates already did `value or ""`
        for falsy input; the shared resolver now does this uniformly for all
        callers rather than only the ones that happened to add that guard."""
        assert resolve_secret(None) == ""  # type: ignore[arg-type]
