"""Comprehensive tests for cortexflow_ai.autostart — AutostartManager.

Test categories
───────────────
 1. AutostartResult dataclass                    (tests  1–5)
 2. Unsupported platform                         (tests  6–8)
 3. macOS / launchd — enable                    (tests  9–19)
 4. macOS / launchd — disable                   (tests 20–27)
 5. macOS / launchd — status                    (tests 28–32)
 6. Linux / systemd — enable                    (tests 33–44)
 7. Linux / systemd — disable                   (tests 45–52)
 8. Linux / systemd — status                    (tests 53–57)
 9. Windows / registry — enable                 (tests 58–67)
10. Windows / registry — disable                (tests 68–74)
11. Windows / registry — status                 (tests 75–80)
12. _run_cmd safety                             (tests 81–83)
13. CLI integration (autostart group)           (tests 84–92)

All file-system operations use tmp_path. Subprocess side-effects
(_run_cmd) are mocked so CI never calls launchctl / systemctl.
winreg operations are mocked via sys.modules so non-Windows CI passes.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Generator
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

from cortexflow_ai.autostart import (
    AutostartManager,
    AutostartResult,
    _LAUNCHD_FILENAME,
    _LAUNCHD_LABEL,
    _SYSTEMD_FILENAME,
    _SYSTEMD_SERVICE,
    _WINDOWS_REG_VALUE,
)
from cortexflow_ai.cli import cli

FAKE_EXE = "/usr/bin/python3"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _macos(tmp_path: Path, exe: str = FAKE_EXE) -> AutostartManager:
    return AutostartManager(
        executable=exe,
        launchd_dir=tmp_path,
        platform_override="darwin",
    )


def _linux(tmp_path: Path, exe: str = FAKE_EXE) -> AutostartManager:
    return AutostartManager(
        executable=exe,
        systemd_dir=tmp_path,
        platform_override="linux",
    )


@pytest.fixture()
def mock_winreg() -> Generator[MagicMock, None, None]:
    """Inject a fake winreg module so Windows tests run on any OS."""
    mod = MagicMock(spec=ModuleType)
    mod.HKEY_CURRENT_USER = 0x80000001
    mod.REG_SZ = 1
    mod.KEY_SET_VALUE = 0x0002
    mod.KEY_READ = 0x20019
    mod.OpenKey = MagicMock(return_value=MagicMock())
    mod.CloseKey = MagicMock()
    mod.QueryValueEx = MagicMock(side_effect=FileNotFoundError)
    mod.SetValueEx = MagicMock()
    mod.DeleteValue = MagicMock()
    with patch.dict(sys.modules, {"winreg": mod}):
        yield mod


def _windows(exe: str = FAKE_EXE) -> AutostartManager:
    return AutostartManager(executable=exe, platform_override="win32")


# ─────────────────────────────────────────────────────────────────────────────
# 1. AutostartResult dataclass
# ─────────────────────────────────────────────────────────────────────────────

def test_result_default_fields() -> None:
    r = AutostartResult(success=True, platform="linux", message="ok")
    assert r.success is True
    assert r.platform == "linux"
    assert r.message == "ok"
    assert r.enabled is False
    assert r.entry_path is None
    assert r.already_set is False


def test_result_all_fields() -> None:
    r = AutostartResult(
        success=False, platform="darwin", message="err",
        enabled=True, entry_path="/tmp/x.plist", already_set=True,
    )
    assert r.entry_path == "/tmp/x.plist"
    assert r.already_set is True
    assert r.enabled is True


def test_result_success_false() -> None:
    r = AutostartResult(success=False, platform="win32", message="fail")
    assert not r.success


def test_result_platform_stored() -> None:
    for plat in ("win32", "darwin", "linux"):
        r = AutostartResult(success=True, platform=plat, message="")
        assert r.platform == plat


def test_result_is_dataclass() -> None:
    import dataclasses
    assert dataclasses.is_dataclass(AutostartResult)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Unsupported platform
# ─────────────────────────────────────────────────────────────────────────────

def test_enable_unsupported_platform() -> None:
    mgr = AutostartManager(platform_override="freebsd")
    r = mgr.enable()
    assert not r.success
    assert "freebsd" in r.message.lower() or "unsupported" in r.message.lower()


def test_disable_unsupported_platform() -> None:
    mgr = AutostartManager(platform_override="freebsd")
    r = mgr.disable()
    assert not r.success


def test_status_unsupported_platform() -> None:
    mgr = AutostartManager(platform_override="sunos5")
    r = mgr.status()
    assert not r.success
    assert r.platform == "sunos5"


# ─────────────────────────────────────────────────────────────────────────────
# 3. macOS / launchd — enable
# ─────────────────────────────────────────────────────────────────────────────

def test_macos_enable_creates_plist_file(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        r = _macos(tmp_path).enable()
    assert r.success
    assert (tmp_path / _LAUNCHD_FILENAME).exists()


def test_macos_enable_plist_is_valid_xml(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path).enable()
    content = (tmp_path / _LAUNCHD_FILENAME).read_text()
    ET.fromstring(content)  # raises if invalid XML


def test_macos_enable_plist_contains_label(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path).enable()
    assert _LAUNCHD_LABEL in (tmp_path / _LAUNCHD_FILENAME).read_text()


def test_macos_enable_plist_run_at_load(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path).enable()
    assert "<true/>" in (tmp_path / _LAUNCHD_FILENAME).read_text()


def test_macos_enable_plist_contains_executable(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path, exe="/custom/python").enable()
    assert "/custom/python" in (tmp_path / _LAUNCHD_FILENAME).read_text()


def test_macos_enable_plist_contains_module_args(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path).enable()
    content = (tmp_path / _LAUNCHD_FILENAME).read_text()
    assert "cortexflow_ai" in content
    assert "start" in content


def test_macos_enable_calls_launchctl_load(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        _macos(tmp_path).enable()
    plist_path = str(tmp_path / _LAUNCHD_FILENAME)
    mock_cmd.assert_called_once_with(["launchctl", "load", "-w", plist_path])


def test_macos_enable_returns_enabled_true(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        r = _macos(tmp_path).enable()
    assert r.enabled is True


def test_macos_enable_result_has_entry_path(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        r = _macos(tmp_path).enable()
    assert r.entry_path == str(tmp_path / _LAUNCHD_FILENAME)


def test_macos_enable_creates_dir_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "LaunchAgents"
    mgr = AutostartManager(executable=FAKE_EXE, launchd_dir=nested, platform_override="darwin")
    with patch.object(AutostartManager, "_run_cmd"):
        r = mgr.enable()
    assert r.success
    assert nested.exists()


def test_macos_enable_already_registered(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path).enable()  # first call
        r = _macos(tmp_path).enable()  # second call — already exists
    assert r.success
    assert r.already_set is True
    assert r.enabled is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. macOS / launchd — disable
# ─────────────────────────────────────────────────────────────────────────────

def test_macos_disable_removes_plist(tmp_path: Path) -> None:
    plist = tmp_path / _LAUNCHD_FILENAME
    plist.write_text("<plist/>")
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path).disable()
    assert not plist.exists()


def test_macos_disable_calls_launchctl_unload(tmp_path: Path) -> None:
    plist = tmp_path / _LAUNCHD_FILENAME
    plist.write_text("<plist/>")
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        _macos(tmp_path).disable()
    mock_cmd.assert_called_once_with(["launchctl", "unload", "-w", str(plist)])


def test_macos_disable_returns_enabled_false(tmp_path: Path) -> None:
    plist = tmp_path / _LAUNCHD_FILENAME
    plist.write_text("<plist/>")
    with patch.object(AutostartManager, "_run_cmd"):
        r = _macos(tmp_path).disable()
    assert r.enabled is False


def test_macos_disable_when_not_registered(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        r = _macos(tmp_path).disable()
    assert r.success
    assert r.already_set is True
    mock_cmd.assert_not_called()


def test_macos_disable_result_has_entry_path(tmp_path: Path) -> None:
    plist = tmp_path / _LAUNCHD_FILENAME
    plist.write_text("<plist/>")
    with patch.object(AutostartManager, "_run_cmd"):
        r = _macos(tmp_path).disable()
    assert r.entry_path == str(plist)


def test_macos_disable_platform_is_darwin(tmp_path: Path) -> None:
    plist = tmp_path / _LAUNCHD_FILENAME
    plist.write_text("<plist/>")
    with patch.object(AutostartManager, "_run_cmd"):
        r = _macos(tmp_path).disable()
    assert r.platform == "darwin"


def test_macos_enable_disable_roundtrip(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _macos(tmp_path).enable()
        r = _macos(tmp_path).disable()
    assert r.success
    assert not (tmp_path / _LAUNCHD_FILENAME).exists()


def test_macos_disable_not_registered_no_cmd(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        _macos(tmp_path).disable()
    mock_cmd.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 5. macOS / launchd — status
# ─────────────────────────────────────────────────────────────────────────────

def test_macos_status_disabled_when_no_plist(tmp_path: Path) -> None:
    r = _macos(tmp_path).status()
    assert r.success
    assert r.enabled is False


def test_macos_status_enabled_when_plist_exists(tmp_path: Path) -> None:
    (tmp_path / _LAUNCHD_FILENAME).write_text("<plist/>")
    r = _macos(tmp_path).status()
    assert r.enabled is True


def test_macos_status_entry_path_always_set(tmp_path: Path) -> None:
    r = _macos(tmp_path).status()
    assert r.entry_path is not None
    assert _LAUNCHD_FILENAME in r.entry_path


def test_macos_status_message_contains_enabled(tmp_path: Path) -> None:
    (tmp_path / _LAUNCHD_FILENAME).write_text("<plist/>")
    r = _macos(tmp_path).status()
    assert "enabled" in r.message.lower()


def test_macos_status_platform_is_darwin(tmp_path: Path) -> None:
    r = _macos(tmp_path).status()
    assert r.platform == "darwin"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Linux / systemd — enable
# ─────────────────────────────────────────────────────────────────────────────

def test_linux_enable_creates_unit_file(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        r = _linux(tmp_path).enable()
    assert r.success
    assert (tmp_path / _SYSTEMD_FILENAME).exists()


def test_linux_enable_unit_has_exec_start(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _linux(tmp_path, exe="/opt/python").enable()
    content = (tmp_path / _SYSTEMD_FILENAME).read_text()
    assert "ExecStart=/opt/python -m cortexflow_ai start" in content


def test_linux_enable_unit_has_restart_policy(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _linux(tmp_path).enable()
    content = (tmp_path / _SYSTEMD_FILENAME).read_text()
    assert "Restart=on-failure" in content


def test_linux_enable_unit_has_wants_default_target(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _linux(tmp_path).enable()
    assert "WantedBy=default.target" in (tmp_path / _SYSTEMD_FILENAME).read_text()


def test_linux_enable_unit_has_description(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _linux(tmp_path).enable()
    assert "Description=" in (tmp_path / _SYSTEMD_FILENAME).read_text()


def test_linux_enable_calls_daemon_reload(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        _linux(tmp_path).enable()
    calls = mock_cmd.call_args_list
    assert call(["systemctl", "--user", "daemon-reload"]) in calls


def test_linux_enable_calls_systemctl_enable(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        _linux(tmp_path).enable()
    calls = mock_cmd.call_args_list
    assert call(["systemctl", "--user", "enable", _SYSTEMD_SERVICE]) in calls


def test_linux_enable_daemon_reload_before_enable(tmp_path: Path) -> None:
    calls_log: list[list[str]] = []
    def record(cmd: list[str]) -> None:
        calls_log.append(cmd)
    with patch.object(AutostartManager, "_run_cmd", side_effect=record):
        _linux(tmp_path).enable()
    reload_idx = next(i for i, c in enumerate(calls_log) if "daemon-reload" in c)
    enable_idx = next(i for i, c in enumerate(calls_log) if "enable" in c)
    assert reload_idx < enable_idx


def test_linux_enable_returns_enabled_true(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        r = _linux(tmp_path).enable()
    assert r.enabled is True


def test_linux_enable_result_has_entry_path(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        r = _linux(tmp_path).enable()
    assert r.entry_path == str(tmp_path / _SYSTEMD_FILENAME)


def test_linux_enable_creates_dir_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "systemd" / "user"
    mgr = AutostartManager(executable=FAKE_EXE, systemd_dir=nested, platform_override="linux")
    with patch.object(AutostartManager, "_run_cmd"):
        r = mgr.enable()
    assert r.success
    assert nested.exists()


def test_linux_enable_already_registered(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _linux(tmp_path).enable()
        r = _linux(tmp_path).enable()
    assert r.success
    assert r.already_set is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. Linux / systemd — disable
# ─────────────────────────────────────────────────────────────────────────────

def test_linux_disable_removes_unit_file(tmp_path: Path) -> None:
    unit = tmp_path / _SYSTEMD_FILENAME
    unit.write_text("[Unit]")
    with patch.object(AutostartManager, "_run_cmd"):
        _linux(tmp_path).disable()
    assert not unit.exists()


def test_linux_disable_calls_systemctl_disable(tmp_path: Path) -> None:
    (tmp_path / _SYSTEMD_FILENAME).write_text("[Unit]")
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        _linux(tmp_path).disable()
    calls = mock_cmd.call_args_list
    assert call(["systemctl", "--user", "disable", _SYSTEMD_SERVICE]) in calls


def test_linux_disable_calls_daemon_reload_after(tmp_path: Path) -> None:
    calls_log: list[list[str]] = []
    (tmp_path / _SYSTEMD_FILENAME).write_text("[Unit]")
    def record(cmd: list[str]) -> None:
        calls_log.append(cmd)
    with patch.object(AutostartManager, "_run_cmd", side_effect=record):
        _linux(tmp_path).disable()
    assert any("daemon-reload" in c for c in calls_log)


def test_linux_disable_when_not_registered(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        r = _linux(tmp_path).disable()
    assert r.success
    assert r.already_set is True
    mock_cmd.assert_not_called()


def test_linux_disable_returns_enabled_false(tmp_path: Path) -> None:
    (tmp_path / _SYSTEMD_FILENAME).write_text("[Unit]")
    with patch.object(AutostartManager, "_run_cmd"):
        r = _linux(tmp_path).disable()
    assert r.enabled is False


def test_linux_enable_disable_roundtrip(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd"):
        _linux(tmp_path).enable()
        r = _linux(tmp_path).disable()
    assert r.success
    assert not (tmp_path / _SYSTEMD_FILENAME).exists()


def test_linux_disable_platform_is_linux(tmp_path: Path) -> None:
    (tmp_path / _SYSTEMD_FILENAME).write_text("[Unit]")
    with patch.object(AutostartManager, "_run_cmd"):
        r = _linux(tmp_path).disable()
    assert r.platform == "linux"


def test_linux_disable_no_cmd_when_no_file(tmp_path: Path) -> None:
    with patch.object(AutostartManager, "_run_cmd") as mock_cmd:
        _linux(tmp_path).disable()
    mock_cmd.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 8. Linux / systemd — status
# ─────────────────────────────────────────────────────────────────────────────

def test_linux_status_disabled_when_no_unit(tmp_path: Path) -> None:
    r = _linux(tmp_path).status()
    assert r.success
    assert r.enabled is False


def test_linux_status_enabled_when_unit_exists(tmp_path: Path) -> None:
    (tmp_path / _SYSTEMD_FILENAME).write_text("[Unit]")
    r = _linux(tmp_path).status()
    assert r.enabled is True


def test_linux_status_entry_path_always_set(tmp_path: Path) -> None:
    r = _linux(tmp_path).status()
    assert r.entry_path is not None
    assert _SYSTEMD_FILENAME in r.entry_path


def test_linux_status_message_contains_disabled(tmp_path: Path) -> None:
    r = _linux(tmp_path).status()
    assert "disabled" in r.message.lower()


def test_linux_status_platform_is_linux(tmp_path: Path) -> None:
    r = _linux(tmp_path).status()
    assert r.platform == "linux"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Windows / registry — enable
# ─────────────────────────────────────────────────────────────────────────────

def test_windows_enable_calls_open_key(mock_winreg: MagicMock) -> None:
    _windows().enable()
    mock_winreg.OpenKey.assert_called()


def test_windows_enable_calls_set_value_ex(mock_winreg: MagicMock) -> None:
    _windows().enable()
    mock_winreg.SetValueEx.assert_called()


def test_windows_enable_value_name_is_correct(mock_winreg: MagicMock) -> None:
    _windows(exe="C:\\Python\\python.exe").enable()
    args = mock_winreg.SetValueEx.call_args[0]
    assert args[1] == _WINDOWS_REG_VALUE


def test_windows_enable_value_contains_executable(mock_winreg: MagicMock) -> None:
    _windows(exe="C:\\Python\\python.exe").enable()
    args = mock_winreg.SetValueEx.call_args[0]
    value_str = args[4]
    assert "C:\\Python\\python.exe" in value_str


def test_windows_enable_value_contains_module_flag(mock_winreg: MagicMock) -> None:
    _windows().enable()
    args = mock_winreg.SetValueEx.call_args[0]
    value_str = args[4]
    assert "-m cortexflow_ai start" in value_str


def test_windows_enable_value_is_reg_sz(mock_winreg: MagicMock) -> None:
    _windows().enable()
    args = mock_winreg.SetValueEx.call_args[0]
    assert args[3] == mock_winreg.REG_SZ


def test_windows_enable_returns_enabled_true(mock_winreg: MagicMock) -> None:
    r = _windows().enable()
    assert r.enabled is True


def test_windows_enable_platform_is_win32(mock_winreg: MagicMock) -> None:
    r = _windows().enable()
    assert r.platform == "win32"


def test_windows_enable_already_registered_returns_already_set(mock_winreg: MagicMock) -> None:
    mgr = _windows(exe=FAKE_EXE)
    expected_cmd = mgr.windows_command()
    mock_winreg.QueryValueEx.side_effect = None
    mock_winreg.QueryValueEx.return_value = (expected_cmd, 1)
    r = mgr.enable()
    assert r.already_set is True
    assert r.enabled is True
    mock_winreg.SetValueEx.assert_not_called()


def test_windows_command_quoted_executable() -> None:
    mgr = _windows(exe="C:\\Program Files\\Python\\python.exe")
    cmd = mgr.windows_command()
    assert cmd.startswith('"C:\\Program Files\\Python\\python.exe"')


# ─────────────────────────────────────────────────────────────────────────────
# 10. Windows / registry — disable
# ─────────────────────────────────────────────────────────────────────────────

def test_windows_disable_calls_delete_value(mock_winreg: MagicMock) -> None:
    _windows().disable()
    mock_winreg.DeleteValue.assert_called()


def test_windows_disable_deletes_correct_value(mock_winreg: MagicMock) -> None:
    _windows().disable()
    args = mock_winreg.DeleteValue.call_args[0]
    assert args[1] == _WINDOWS_REG_VALUE


def test_windows_disable_returns_enabled_false(mock_winreg: MagicMock) -> None:
    r = _windows().disable()
    assert r.enabled is False


def test_windows_disable_when_not_registered(mock_winreg: MagicMock) -> None:
    mock_winreg.DeleteValue.side_effect = FileNotFoundError
    r = _windows().disable()
    assert r.success
    assert r.already_set is True
    assert r.enabled is False


def test_windows_disable_platform_is_win32(mock_winreg: MagicMock) -> None:
    r = _windows().disable()
    assert r.platform == "win32"


def test_windows_disable_success_true(mock_winreg: MagicMock) -> None:
    r = _windows().disable()
    assert r.success is True


def test_windows_disable_message_mentions_removal(mock_winreg: MagicMock) -> None:
    r = _windows().disable()
    assert "removed" in r.message.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 11. Windows / registry — status
# ─────────────────────────────────────────────────────────────────────────────

def test_windows_status_enabled_when_key_exists(mock_winreg: MagicMock) -> None:
    mock_winreg.QueryValueEx.side_effect = None
    mock_winreg.QueryValueEx.return_value = ("python.exe -m cortexflow_ai start", 1)
    r = _windows().status()
    assert r.enabled is True
    assert r.success is True


def test_windows_status_disabled_when_key_missing(mock_winreg: MagicMock) -> None:
    mock_winreg.QueryValueEx.side_effect = FileNotFoundError
    r = _windows().status()
    assert r.enabled is False
    assert r.success is True


def test_windows_status_platform_is_win32(mock_winreg: MagicMock) -> None:
    r = _windows().status()
    assert r.platform == "win32"


def test_windows_status_message_contains_enabled(mock_winreg: MagicMock) -> None:
    mock_winreg.QueryValueEx.side_effect = None
    mock_winreg.QueryValueEx.return_value = ("python.exe -m cortexflow_ai start", 1)
    r = _windows().status()
    assert "enabled" in r.message.lower()


def test_windows_status_message_contains_disabled(mock_winreg: MagicMock) -> None:
    mock_winreg.QueryValueEx.side_effect = FileNotFoundError
    r = _windows().status()
    assert "disabled" in r.message.lower()


def test_windows_status_no_entry_path(mock_winreg: MagicMock) -> None:
    r = _windows().status()
    assert r.entry_path is None


# ─────────────────────────────────────────────────────────────────────────────
# 12. _run_cmd safety
# ─────────────────────────────────────────────────────────────────────────────

def test_run_cmd_ignores_nonzero_exit(tmp_path: Path) -> None:
    mgr = _linux(tmp_path)
    mgr._run_cmd([sys.executable, "-c", "import sys; sys.exit(1)"])  # must not raise


def test_run_cmd_ignores_missing_binary(tmp_path: Path) -> None:
    mgr = _linux(tmp_path)
    mgr._run_cmd(["xyzzy_no_such_binary_12345"])  # must not raise


def test_run_cmd_ignores_exception(tmp_path: Path) -> None:
    mgr = _linux(tmp_path)
    with patch("subprocess.run", side_effect=OSError("denied")):
        mgr._run_cmd(["anything"])  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 13. CLI integration (autostart group)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_cli_autostart_enable_exits_zero(tmp_path: Path, runner: CliRunner) -> None:
    with patch("cortexflow_ai.autostart.AutostartManager.enable") as mock_e:
        mock_e.return_value = AutostartResult(
            success=True, platform="linux", message="Done", enabled=True
        )
        result = runner.invoke(cli, ["autostart", "enable"])
    assert result.exit_code == 0


def test_cli_autostart_enable_prints_message(tmp_path: Path, runner: CliRunner) -> None:
    with patch("cortexflow_ai.autostart.AutostartManager.enable") as mock_e:
        mock_e.return_value = AutostartResult(
            success=True, platform="linux", message="Registered!", enabled=True
        )
        result = runner.invoke(cli, ["autostart", "enable"])
    assert "Registered!" in result.output


def test_cli_autostart_enable_exits_one_on_failure(runner: CliRunner) -> None:
    with patch("cortexflow_ai.autostart.AutostartManager.enable") as mock_e:
        mock_e.return_value = AutostartResult(
            success=False, platform="freebsd", message="Unsupported"
        )
        result = runner.invoke(cli, ["autostart", "enable"])
    assert result.exit_code == 1


def test_cli_autostart_disable_exits_zero(runner: CliRunner) -> None:
    with patch("cortexflow_ai.autostart.AutostartManager.disable") as mock_d:
        mock_d.return_value = AutostartResult(
            success=True, platform="linux", message="Removed", enabled=False
        )
        result = runner.invoke(cli, ["autostart", "disable"])
    assert result.exit_code == 0


def test_cli_autostart_disable_prints_message(runner: CliRunner) -> None:
    with patch("cortexflow_ai.autostart.AutostartManager.disable") as mock_d:
        mock_d.return_value = AutostartResult(
            success=True, platform="linux", message="Removed!", enabled=False
        )
        result = runner.invoke(cli, ["autostart", "disable"])
    assert "Removed!" in result.output


def test_cli_autostart_status_exits_zero(runner: CliRunner) -> None:
    with patch("cortexflow_ai.autostart.AutostartManager.status") as mock_s:
        mock_s.return_value = AutostartResult(
            success=True, platform="linux", message="ENABLED", enabled=True,
            entry_path="/home/user/.config/systemd/user/cortexflow.service"
        )
        result = runner.invoke(cli, ["autostart", "status"])
    assert result.exit_code == 0


def test_cli_autostart_status_shows_entry_path(runner: CliRunner) -> None:
    with patch("cortexflow_ai.autostart.AutostartManager.status") as mock_s:
        mock_s.return_value = AutostartResult(
            success=True, platform="linux", message="ENABLED", enabled=True,
            entry_path="/etc/systemd/cortexflow.service"
        )
        result = runner.invoke(cli, ["autostart", "status"])
    assert "/etc/systemd/cortexflow.service" in result.output


def test_cli_autostart_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["autostart", "--help"])
    assert "enable" in result.output
    assert "disable" in result.output
    assert "status" in result.output
