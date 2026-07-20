"""OS autostart registration for NeuralCleave.

Registers ``cortex start`` as a login-time autostart entry so the gateway
launches without requiring a terminal session.

Platform support
────────────────
Windows  → HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (registry)
macOS    → ~/Library/LaunchAgents/ai.neuralcleave.plist          (launchd)
Linux    → ~/.config/systemd/user/NeuralCleave.service           (systemd user)

All public methods return :class:`AutostartResult` and never raise.
Subprocess side-effects (launchctl, systemctl) are isolated in
``_run_cmd`` so tests can patch a single call site.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────

_WINDOWS_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_WINDOWS_REG_VALUE = "NeuralCleave"

_LAUNCHD_LABEL = "ai.neuralcleave"
_LAUNCHD_FILENAME = f"{_LAUNCHD_LABEL}.plist"

_SYSTEMD_SERVICE = "NeuralCleave"
_SYSTEMD_FILENAME = f"{_SYSTEMD_SERVICE}.service"


# ── Result type ──────────────────────────────────────────────────────────────

@dataclass
class AutostartResult:
    """Returned by every :class:`AutostartManager` operation."""

    success: bool
    platform: str
    message: str
    enabled: bool = False
    entry_path: str | None = None
    already_set: bool = False


# ── Manager ──────────────────────────────────────────────────────────────────

class AutostartManager:
    """Cross-platform autostart registration.

    Args:
        executable:        Python interpreter used to launch the gateway.
                           Defaults to :data:`sys.executable`.
        launchd_dir:       Override the LaunchAgents directory (macOS tests).
        systemd_dir:       Override the systemd user-unit directory (Linux tests).
        platform_override: Force a ``sys.platform`` value; used by tests to
                           exercise non-native code paths.
    """

    def __init__(
        self,
        executable: str | None = None,
        launchd_dir: Path | None = None,
        systemd_dir: Path | None = None,
        platform_override: str | None = None,
    ) -> None:
        self._exe = executable or sys.executable
        self._platform = platform_override or sys.platform
        self._launchd_dir = launchd_dir or (Path.home() / "Library" / "LaunchAgents")
        self._systemd_dir = systemd_dir or (Path.home() / ".config" / "systemd" / "user")

    # ── Public API ───────────────────────────────────────────────────────────

    def enable(self) -> AutostartResult:
        """Register NeuralCleave to start at login."""
        if self._platform == "win32":
            return self._windows_enable()
        if self._platform == "darwin":
            return self._macos_enable()
        if self._platform.startswith("linux"):
            return self._linux_enable()
        return _unsupported(self._platform)

    def disable(self) -> AutostartResult:
        """Remove the NeuralCleave autostart entry."""
        if self._platform == "win32":
            return self._windows_disable()
        if self._platform == "darwin":
            return self._macos_disable()
        if self._platform.startswith("linux"):
            return self._linux_disable()
        return _unsupported(self._platform)

    def status(self) -> AutostartResult:
        """Check whether autostart is currently registered."""
        if self._platform == "win32":
            return self._windows_status()
        if self._platform == "darwin":
            return self._macos_status()
        if self._platform.startswith("linux"):
            return self._linux_status()
        return _unsupported(self._platform)

    # ── macOS / launchd ──────────────────────────────────────────────────────

    @property
    def launchd_plist_path(self) -> Path:
        return self._launchd_dir / _LAUNCHD_FILENAME

    def build_plist(self) -> str:
        """Return the launchd plist XML for the current executable."""
        log_dir = Path.home() / ".neuralcleave"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
            ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "  <key>Label</key>\n"
            f"  <string>{_LAUNCHD_LABEL}</string>\n"
            "  <key>ProgramArguments</key>\n"
            "  <array>\n"
            f"    <string>{self._exe}</string>\n"
            "    <string>-m</string>\n"
            "    <string>neuralcleave</string>\n"
            "    <string>start</string>\n"
            "  </array>\n"
            "  <key>RunAtLoad</key>\n"
            "  <true/>\n"
            "  <key>KeepAlive</key>\n"
            "  <false/>\n"
            "  <key>StandardOutPath</key>\n"
            f"  <string>{log_dir}/NeuralCleave.log</string>\n"
            "  <key>StandardErrorPath</key>\n"
            f"  <string>{log_dir}/NeuralCleave.err</string>\n"
            "</dict>\n"
            "</plist>\n"
        )

    def _macos_enable(self) -> AutostartResult:
        plist = self.launchd_plist_path
        if plist.exists():
            return AutostartResult(
                success=True,
                platform="darwin",
                message=f"Autostart already registered at {plist}",
                enabled=True,
                entry_path=str(plist),
                already_set=True,
            )
        self._launchd_dir.mkdir(parents=True, exist_ok=True)
        plist.write_text(self.build_plist(), encoding="utf-8")
        self._run_cmd(["launchctl", "load", "-w", str(plist)])
        return AutostartResult(
            success=True,
            platform="darwin",
            message=f"Autostart registered via launchd: {plist}",
            enabled=True,
            entry_path=str(plist),
        )

    def _macos_disable(self) -> AutostartResult:
        plist = self.launchd_plist_path
        if not plist.exists():
            return AutostartResult(
                success=True,
                platform="darwin",
                message="Autostart was not registered.",
                enabled=False,
                already_set=True,
            )
        self._run_cmd(["launchctl", "unload", "-w", str(plist)])
        plist.unlink()
        return AutostartResult(
            success=True,
            platform="darwin",
            message=f"Autostart removed: {plist}",
            enabled=False,
            entry_path=str(plist),
        )

    def _macos_status(self) -> AutostartResult:
        plist = self.launchd_plist_path
        active = plist.exists()
        return AutostartResult(
            success=True,
            platform="darwin",
            message=f"Autostart is {'ENABLED' if active else 'DISABLED'} ({plist})",
            enabled=active,
            entry_path=str(plist),
        )

    # ── Linux / systemd ──────────────────────────────────────────────────────

    @property
    def systemd_unit_path(self) -> Path:
        return self._systemd_dir / _SYSTEMD_FILENAME

    def build_systemd_unit(self) -> str:
        """Return the systemd unit file contents for the current executable."""
        return (
            "[Unit]\n"
            "Description=NeuralCleave Personal AI Gateway\n"
            "After=network.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={self._exe} -m neuralcleave start\n"
            "Restart=on-failure\n"
            "RestartSec=10\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def _linux_enable(self) -> AutostartResult:
        unit = self.systemd_unit_path
        if unit.exists():
            return AutostartResult(
                success=True,
                platform="linux",
                message=f"Autostart already registered at {unit}",
                enabled=True,
                entry_path=str(unit),
                already_set=True,
            )
        self._systemd_dir.mkdir(parents=True, exist_ok=True)
        unit.write_text(self.build_systemd_unit(), encoding="utf-8")
        self._run_cmd(["systemctl", "--user", "daemon-reload"])
        self._run_cmd(["systemctl", "--user", "enable", _SYSTEMD_SERVICE])
        return AutostartResult(
            success=True,
            platform="linux",
            message=f"Autostart registered via systemd user service: {unit}",
            enabled=True,
            entry_path=str(unit),
        )

    def _linux_disable(self) -> AutostartResult:
        unit = self.systemd_unit_path
        if not unit.exists():
            return AutostartResult(
                success=True,
                platform="linux",
                message="Autostart was not registered.",
                enabled=False,
                already_set=True,
            )
        self._run_cmd(["systemctl", "--user", "disable", _SYSTEMD_SERVICE])
        unit.unlink()
        self._run_cmd(["systemctl", "--user", "daemon-reload"])
        return AutostartResult(
            success=True,
            platform="linux",
            message=f"Autostart removed: {unit}",
            enabled=False,
            entry_path=str(unit),
        )

    def _linux_status(self) -> AutostartResult:
        unit = self.systemd_unit_path
        active = unit.exists()
        return AutostartResult(
            success=True,
            platform="linux",
            message=f"Autostart is {'ENABLED' if active else 'DISABLED'} ({unit})",
            enabled=active,
            entry_path=str(unit),
        )

    # ── Windows / registry ───────────────────────────────────────────────────

    def windows_command(self) -> str:
        """Registry value string that launches the gateway."""
        return f'"{self._exe}" -m neuralcleave start'

    def _windows_enable(self) -> AutostartResult:
        import winreg  # type: ignore[import-not-found]

        cmd = self.windows_command()
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _WINDOWS_REG_KEY, 0, winreg.KEY_SET_VALUE
        )
        try:
            existing, _ = winreg.QueryValueEx(key, _WINDOWS_REG_VALUE)
            if existing == cmd:
                winreg.CloseKey(key)
                return AutostartResult(
                    success=True,
                    platform="win32",
                    message="NeuralCleave autostart is already registered in the registry.",
                    enabled=True,
                    already_set=True,
                )
        except FileNotFoundError:
            pass
        winreg.SetValueEx(key, _WINDOWS_REG_VALUE, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return AutostartResult(
            success=True,
            platform="win32",
            message=f"Registered autostart in HKCU\\{_WINDOWS_REG_KEY} → {_WINDOWS_REG_VALUE}",
            enabled=True,
        )

    def _windows_disable(self) -> AutostartResult:
        import winreg  # type: ignore[import-not-found]

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WINDOWS_REG_KEY, 0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, _WINDOWS_REG_VALUE)
            winreg.CloseKey(key)
        except FileNotFoundError:
            return AutostartResult(
                success=True,
                platform="win32",
                message="NeuralCleave autostart was not registered.",
                enabled=False,
                already_set=True,
            )
        return AutostartResult(
            success=True,
            platform="win32",
            message=f"Removed autostart entry from HKCU\\{_WINDOWS_REG_KEY}",
            enabled=False,
        )

    def _windows_status(self) -> AutostartResult:
        import winreg  # type: ignore[import-not-found]

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WINDOWS_REG_KEY, 0, winreg.KEY_READ
            )
            value, _ = winreg.QueryValueEx(key, _WINDOWS_REG_VALUE)
            winreg.CloseKey(key)
            return AutostartResult(
                success=True,
                platform="win32",
                message=f"Autostart is ENABLED → {value}",
                enabled=True,
            )
        except FileNotFoundError:
            return AutostartResult(
                success=True,
                platform="win32",
                message=f"Autostart is DISABLED (no entry for {_WINDOWS_REG_VALUE!r} in registry).",
                enabled=False,
            )

    # ── Internal ─────────────────────────────────────────────────────────────

    def _run_cmd(self, cmd: list[str]) -> None:
        """Run a side-effect command, ignoring failures (best-effort)."""
        try:
            subprocess.run(cmd, capture_output=True, check=False, timeout=10)
        except Exception:
            pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def _unsupported(platform: str) -> AutostartResult:
    return AutostartResult(
        success=False,
        platform=platform,
        message=(
            f"Unsupported platform {platform!r}. "
            "Autostart must be configured manually."
        ),
    )
