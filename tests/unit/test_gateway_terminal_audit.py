"""Tests for neuralcleave.gateway.terminal_audit.

Round 7 gap analysis P4 (2026-08-30): the embedded terminal ran commands
with no trace of ever having done so. This lightweight, append-only log
is the fix — deliberately separate from PrivacyAuditLog, whose schema is
specific to outbound HTTP calls (method/url/destination), not shell
commands.
"""

from __future__ import annotations

import json

import pytest

from neuralcleave.gateway import terminal_audit


@pytest.fixture()
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "terminal_history.log"
    monkeypatch.setattr(terminal_audit, "DEFAULT_LOG_PATH", str(path))
    return path


def test_record_command_appends_a_json_line(log_path):
    terminal_audit.record_command("ls -la")

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["cmd"] == "ls -la"
    assert isinstance(entry["timestamp"], (int, float))


def test_record_command_appends_multiple_entries_in_order(log_path):
    terminal_audit.record_command("first")
    terminal_audit.record_command("second")

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["cmd"] for line in lines] == ["first", "second"]


def test_record_command_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "nested" / "dir" / "terminal_history.log"
    monkeypatch.setattr(terminal_audit, "DEFAULT_LOG_PATH", str(nested))

    terminal_audit.record_command("echo hi")

    assert nested.exists()


def test_record_command_swallows_write_failures(monkeypatch):
    """A logging failure (disk full, permission denied) must never raise -
    it would otherwise break the terminal itself."""

    def _raise_disk_full():
        raise OSError("disk full")

    monkeypatch.setattr(terminal_audit, "_log_path", _raise_disk_full)

    terminal_audit.record_command("rm -rf /")  # must not raise
