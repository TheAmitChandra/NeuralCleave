"""Tests for the `neuralcleave backup` CLI command group."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from neuralcleave.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    (d / "config.toml").write_text('[agent]\nname = "Bot"\n', encoding="utf-8")
    return d


class TestBackupCreate:
    def test_creates_archive(self, runner: CliRunner, state_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        result = runner.invoke(
            cli,
            ["backup", "create", "--state-dir", str(state_dir), "--backup-dir", str(backup_dir)],
        )
        assert result.exit_code == 0
        assert "Backup created" in result.output
        assert list(backup_dir.glob("neuralcleave-backup-*.tar.gz"))

    def test_missing_state_dir_reports_error(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(
            cli,
            ["backup", "create", "--state-dir", str(tmp_path / "nope"), "--backup-dir", str(tmp_path / "backups")],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestBackupList:
    def test_empty_reports_no_backups(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["backup", "list", "--backup-dir", str(tmp_path / "backups")])
        assert result.exit_code == 0
        assert "No backups found" in result.output

    def test_lists_created_backup(self, runner: CliRunner, state_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        runner.invoke(cli, ["backup", "create", "--state-dir", str(state_dir), "--backup-dir", str(backup_dir)])

        result = runner.invoke(cli, ["backup", "list", "--backup-dir", str(backup_dir)])

        assert result.exit_code == 0
        assert "No backups found" not in result.output
        assert "MB" in result.output


class TestBackupVerify:
    def test_valid_backup_reports_ok(self, runner: CliRunner, state_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        runner.invoke(cli, ["backup", "create", "--state-dir", str(state_dir), "--backup-dir", str(backup_dir)])
        archive = next(backup_dir.glob("neuralcleave-backup-*.tar.gz"))

        result = runner.invoke(cli, ["backup", "verify", str(archive)])

        assert result.exit_code == 0
        assert "Valid backup" in result.output

    def test_invalid_backup_reports_error_and_exits_nonzero(self, runner: CliRunner, tmp_path: Path) -> None:
        bad = tmp_path / "corrupt.tar.gz"
        bad.write_bytes(b"not a tar file")

        result = runner.invoke(cli, ["backup", "verify", str(bad)])

        assert result.exit_code != 0
        assert "Invalid backup" in result.output


class TestBackupRestore:
    def test_aborts_without_yes(self, runner: CliRunner, state_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        runner.invoke(cli, ["backup", "create", "--state-dir", str(state_dir), "--backup-dir", str(backup_dir)])
        archive = next(backup_dir.glob("neuralcleave-backup-*.tar.gz"))

        result = runner.invoke(
            cli, ["backup", "restore", str(archive), "--target", str(tmp_path / "restored")], input="n\n"
        )

        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_restores_with_yes_flag(self, runner: CliRunner, state_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        runner.invoke(cli, ["backup", "create", "--state-dir", str(state_dir), "--backup-dir", str(backup_dir)])
        archive = next(backup_dir.glob("neuralcleave-backup-*.tar.gz"))
        target = tmp_path / "restored"

        result = runner.invoke(cli, ["backup", "restore", str(archive), "--target", str(target), "--yes"])

        assert result.exit_code == 0
        assert "Restored to" in result.output
        assert (target / "neuralcleave-state" / "config.toml").exists()

    def test_refuses_nonempty_target_without_force(self, runner: CliRunner, state_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        runner.invoke(cli, ["backup", "create", "--state-dir", str(state_dir), "--backup-dir", str(backup_dir)])
        archive = next(backup_dir.glob("neuralcleave-backup-*.tar.gz"))
        target = tmp_path / "restored"
        target.mkdir()
        (target / "existing.txt").write_text("already here")

        result = runner.invoke(cli, ["backup", "restore", str(archive), "--target", str(target), "--yes"])

        assert result.exit_code != 0
        assert "not empty" in result.output.lower()

    def test_force_restores_into_nonempty_target(self, runner: CliRunner, state_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        runner.invoke(cli, ["backup", "create", "--state-dir", str(state_dir), "--backup-dir", str(backup_dir)])
        archive = next(backup_dir.glob("neuralcleave-backup-*.tar.gz"))
        target = tmp_path / "restored"
        target.mkdir()
        (target / "existing.txt").write_text("already here")

        result = runner.invoke(
            cli, ["backup", "restore", str(archive), "--target", str(target), "--yes", "--force"]
        )

        assert result.exit_code == 0
        assert (target / "neuralcleave-state" / "config.toml").exists()
