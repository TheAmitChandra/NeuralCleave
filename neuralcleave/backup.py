"""State backup & restore — tar the NeuralCleave state directory to a single
archive, verify its integrity, and restore it to a fresh target.

The "state directory" is ``~/.neuralcleave`` by default: ``config.toml``,
``memory.db``, ``privacy_audit.db``, and the ``skills/`` directory all live
there, so backing up that one directory captures everything a user needs to
recover after data loss or a machine migration. There was previously no
first-party backup/restore path at all (P1 of the 2026-08-17 gap analysis).

Usage::

    from neuralcleave.backup import create_backup, verify_backup, restore_backup, list_backups

    path = create_backup()          # -> ~/.neuralcleave-backups/neuralcleave-backup-<stamp>.tar.gz
    ok, reason = verify_backup(path)
    restore_backup(path, target_dir="/fresh/restore/location")
    backups = list_backups()
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".neuralcleave"
DEFAULT_BACKUP_DIR = Path.home() / ".neuralcleave-backups"
ARCHIVE_ROOT = "neuralcleave-state"
MANIFEST_PATH = "neuralcleave-state-manifest/backup_manifest.json"


@dataclass
class BackupInfo:
    """Metadata about one backup archive."""

    path: Path
    size_bytes: int
    created_at: str  # from the manifest, or the filename timestamp as fallback

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def create_backup(
    state_dir: str | Path = DEFAULT_STATE_DIR,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
) -> Path:
    """Create a timestamped ``tar.gz`` archive of *state_dir*.

    Writes the archive plus a ``.sha256`` checksum sidecar file into
    *backup_dir*. Returns the archive path.

    Raises FileNotFoundError if *state_dir* doesn't exist.
    """
    state_dir = Path(state_dir).expanduser()
    backup_dir = Path(backup_dir).expanduser()
    if not state_dir.exists():
        raise FileNotFoundError(f"State directory not found: {state_dir}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    archive_path = backup_dir / f"neuralcleave-backup-{stamp}.tar.gz"

    manifest = {"created_at": stamp, "source_dir": str(state_dir)}
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(state_dir, arcname=ARCHIVE_ROOT)
        info = tarfile.TarInfo(name=MANIFEST_PATH)
        info.size = len(manifest_bytes)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(manifest_bytes))

    checksum = _sha256_file(archive_path)
    checksum_path = archive_path.with_name(archive_path.name + ".sha256")
    checksum_path.write_text(f"{checksum}  {archive_path.name}\n")

    return archive_path


def verify_backup(archive_path: str | Path) -> tuple[bool, str]:
    """Verify a backup archive's integrity.

    Checks that the archive is a readable ``tar.gz`` and, if a ``.sha256``
    sidecar file exists alongside it, that the checksum matches.

    Returns ``(ok, reason)`` — *reason* is empty on success, otherwise a
    short human-readable explanation of the failure.
    """
    archive_path = Path(archive_path).expanduser()
    if not archive_path.exists():
        return False, f"Archive not found: {archive_path}"

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.getmembers()
    except (tarfile.TarError, OSError) as exc:
        return False, f"Archive is not a valid tar.gz: {exc}"

    checksum_path = archive_path.with_name(archive_path.name + ".sha256")
    if checksum_path.exists():
        expected = checksum_path.read_text().split()[0]
        actual = _sha256_file(archive_path)
        if expected != actual:
            return False, f"Checksum mismatch: expected {expected}, got {actual}"

    return True, ""


def _created_at_from_manifest(archive_path: Path) -> str | None:
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            member = tar.getmember(MANIFEST_PATH)
            data = tar.extractfile(member)
            if data is None:
                return None
            manifest = json.loads(data.read().decode("utf-8"))
            return manifest.get("created_at")
    except (KeyError, tarfile.TarError, OSError, json.JSONDecodeError):
        return None


def _timestamp_from_filename(name: str) -> str:
    stem = name.removeprefix("neuralcleave-backup-").removesuffix(".tar.gz")
    return stem


def list_backups(backup_dir: str | Path = DEFAULT_BACKUP_DIR) -> list[BackupInfo]:
    """List backup archives in *backup_dir*, newest first."""
    backup_dir = Path(backup_dir).expanduser()
    if not backup_dir.exists():
        return []

    infos: list[BackupInfo] = []
    for path in backup_dir.glob("neuralcleave-backup-*.tar.gz"):
        created_at = _created_at_from_manifest(path) or _timestamp_from_filename(path.name)
        infos.append(BackupInfo(path=path, size_bytes=path.stat().st_size, created_at=created_at))
    infos.sort(key=lambda b: b.created_at, reverse=True)
    return infos


def restore_backup(
    archive_path: str | Path,
    target_dir: str | Path,
    *,
    force: bool = False,
) -> Path:
    """Extract a backup archive to *target_dir*.

    *target_dir* must not already exist, or must be empty, unless *force* is
    set — a restore can never silently overwrite live state by default
    ("fresh-target-only"). Extraction uses tarfile's ``"data"`` filter to
    reject path traversal, absolute paths, and other unsafe archive members.

    Returns the path to the restored state directory
    (``target_dir/neuralcleave-state``).
    """
    archive_path = Path(archive_path).expanduser()
    target_dir = Path(target_dir).expanduser()

    ok, reason = verify_backup(archive_path)
    if not ok:
        raise ValueError(f"Refusing to restore an invalid backup: {reason}")

    if target_dir.exists() and any(target_dir.iterdir()) and not force:
        raise FileExistsError(
            f"Target directory is not empty: {target_dir} (pass force=True to override)"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.name.startswith(f"{ARCHIVE_ROOT}/")]
        tar.extractall(target_dir, members=members, filter="data")

    return target_dir / ARCHIVE_ROOT
