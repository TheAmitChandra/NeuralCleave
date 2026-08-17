"""Tests for neuralcleave.backup — create/verify/list/restore state archives.

Covers P1 of the 2026-08-17 gap analysis: NeuralCleave previously had no
first-party backup/restore path for the state directory (config.toml,
memory.db, privacy_audit.db, skills/).
"""

from __future__ import annotations

import io
import json
import tarfile

import pytest

from neuralcleave.backup import (
    ARCHIVE_ROOT,
    BackupInfo,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)


@pytest.fixture()
def state_dir(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    (d / "config.toml").write_text("[agent]\nname = 'test'\n")
    (d / "memory.db").write_bytes(b"fake-sqlite-bytes")
    (d / "skills").mkdir()
    (d / "skills" / "example").mkdir()
    (d / "skills" / "example" / "skill.py").write_text("def run(): pass\n")
    return d


class TestCreateBackup:
    def test_creates_archive_file(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "backups"
        archive = create_backup(state_dir=state_dir, backup_dir=backup_dir)
        assert archive.exists()
        assert archive.name.startswith("neuralcleave-backup-")
        assert archive.suffix == ".gz"

    def test_creates_checksum_sidecar(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "backups"
        archive = create_backup(state_dir=state_dir, backup_dir=backup_dir)
        sidecar = archive.with_name(archive.name + ".sha256")
        assert sidecar.exists()
        assert archive.name in sidecar.read_text()

    def test_archive_contains_all_state_files(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "backups"
        archive = create_backup(state_dir=state_dir, backup_dir=backup_dir)
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
        assert f"{ARCHIVE_ROOT}/config.toml" in names
        assert f"{ARCHIVE_ROOT}/memory.db" in names
        assert f"{ARCHIVE_ROOT}/skills/example/skill.py" in names

    def test_archive_contains_manifest_with_source_dir(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "backups"
        archive = create_backup(state_dir=state_dir, backup_dir=backup_dir)
        with tarfile.open(archive, "r:gz") as tar:
            member = tar.getmember("neuralcleave-state-manifest/backup_manifest.json")
            manifest = json.loads(tar.extractfile(member).read())
        assert manifest["source_dir"] == str(state_dir)
        assert "created_at" in manifest

    def test_missing_state_dir_raises(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            create_backup(state_dir=tmp_path / "does-not-exist", backup_dir=tmp_path / "backups")

    def test_creates_backup_dir_if_missing(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "nested" / "backups"
        create_backup(state_dir=state_dir, backup_dir=backup_dir)
        assert backup_dir.exists()


class TestVerifyBackup:
    def test_valid_archive_verifies_ok(self, state_dir, tmp_path) -> None:
        archive = create_backup(state_dir=state_dir, backup_dir=tmp_path / "backups")
        ok, reason = verify_backup(archive)
        assert ok is True
        assert reason == ""

    def test_missing_archive_fails(self, tmp_path) -> None:
        ok, reason = verify_backup(tmp_path / "nope.tar.gz")
        assert ok is False
        assert "not found" in reason.lower()

    def test_corrupted_archive_fails(self, tmp_path) -> None:
        bad = tmp_path / "corrupt.tar.gz"
        bad.write_bytes(b"not actually a tar file")
        ok, reason = verify_backup(bad)
        assert ok is False
        assert "not a valid tar.gz" in reason

    def test_checksum_mismatch_fails(self, state_dir, tmp_path) -> None:
        archive = create_backup(state_dir=state_dir, backup_dir=tmp_path / "backups")
        sidecar = archive.with_name(archive.name + ".sha256")
        sidecar.write_text(f"0000000000000000000000000000000000000000000000000000000000000000  {archive.name}\n")
        ok, reason = verify_backup(archive)
        assert ok is False
        assert "checksum mismatch" in reason.lower()

    def test_missing_sidecar_still_verifies_ok(self, state_dir, tmp_path) -> None:
        archive = create_backup(state_dir=state_dir, backup_dir=tmp_path / "backups")
        archive.with_name(archive.name + ".sha256").unlink()
        ok, reason = verify_backup(archive)
        assert ok is True


class TestListBackups:
    def test_empty_dir_returns_empty_list(self, tmp_path) -> None:
        assert list_backups(backup_dir=tmp_path / "nope") == []

    def test_lists_created_backups(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "backups"
        create_backup(state_dir=state_dir, backup_dir=backup_dir)
        infos = list_backups(backup_dir=backup_dir)
        assert len(infos) == 1
        assert isinstance(infos[0], BackupInfo)
        assert infos[0].size_bytes > 0

    def test_to_dict_has_expected_keys(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "backups"
        create_backup(state_dir=state_dir, backup_dir=backup_dir)
        info = list_backups(backup_dir=backup_dir)[0]
        d = info.to_dict()
        assert set(d) == {"path", "size_bytes", "created_at"}

    def test_ignores_non_backup_files(self, state_dir, tmp_path) -> None:
        backup_dir = tmp_path / "backups"
        create_backup(state_dir=state_dir, backup_dir=backup_dir)
        (backup_dir / "unrelated.txt").write_text("hello")
        infos = list_backups(backup_dir=backup_dir)
        assert len(infos) == 1


class TestRestoreBackup:
    def test_restores_files_to_target(self, state_dir, tmp_path) -> None:
        archive = create_backup(state_dir=state_dir, backup_dir=tmp_path / "backups")
        target = tmp_path / "restored"
        restored_state = restore_backup(archive, target)
        assert (restored_state / "config.toml").read_text() == "[agent]\nname = 'test'\n"
        assert (restored_state / "memory.db").read_bytes() == b"fake-sqlite-bytes"
        assert (restored_state / "skills" / "example" / "skill.py").exists()

    def test_refuses_nonempty_target_without_force(self, state_dir, tmp_path) -> None:
        archive = create_backup(state_dir=state_dir, backup_dir=tmp_path / "backups")
        target = tmp_path / "restored"
        target.mkdir()
        (target / "existing.txt").write_text("already here")
        with pytest.raises(FileExistsError):
            restore_backup(archive, target)

    def test_force_overwrites_nonempty_target(self, state_dir, tmp_path) -> None:
        archive = create_backup(state_dir=state_dir, backup_dir=tmp_path / "backups")
        target = tmp_path / "restored"
        target.mkdir()
        (target / "existing.txt").write_text("already here")
        restored_state = restore_backup(archive, target, force=True)
        assert (restored_state / "config.toml").exists()

    def test_empty_existing_target_does_not_need_force(self, state_dir, tmp_path) -> None:
        archive = create_backup(state_dir=state_dir, backup_dir=tmp_path / "backups")
        target = tmp_path / "restored"
        target.mkdir()  # exists but empty
        restored_state = restore_backup(archive, target)
        assert (restored_state / "config.toml").exists()

    def test_refuses_invalid_backup(self, tmp_path) -> None:
        bad = tmp_path / "corrupt.tar.gz"
        bad.write_bytes(b"not a tar file")
        with pytest.raises(ValueError, match="invalid backup"):
            restore_backup(bad, tmp_path / "target")

    def test_rejects_path_traversal_member(self, tmp_path) -> None:
        archive = tmp_path / "malicious.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(name=f"{ARCHIVE_ROOT}/../../evil.txt")
            data = b"pwned"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        target = tmp_path / "target"
        with pytest.raises(Exception):
            restore_backup(archive, target)
        assert not (tmp_path / "evil.txt").exists()
