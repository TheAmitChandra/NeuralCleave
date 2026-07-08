"""Comprehensive tests for CortexFlow desktop packaging pipeline.

Validates the complete sidecar build chain without actually running PyInstaller
or Tauri:

  Python entry point   →   PyInstaller spec   →   bundle_backend.ps1
  desktop_launcher.py      cortexflow-backend.spec  (build script)
          ↓
  Tauri configuration files (tauri.conf.json, capabilities/default.json)
          ↓
  Rust sidecar integration (lib.rs patterns)

Test categories
───────────────
 1.  desktop_launcher.py — _default_config_path         (tests  1–  4)
 2.  desktop_launcher.py — CORTEXFLOW_PORT override      (tests  5– 12)
 3.  desktop_launcher.py — config loading + fallback     (tests 13– 20)
 4.  desktop_launcher.py — SIGTERM handler               (tests 21– 25)
 5.  desktop_launcher.py — gateway startup call          (tests 26– 30)
 6.  tauri.conf.json — structure & content               (tests 31– 44)
 7.  capabilities/default.json — permissions             (tests 45– 54)
 8.  Cargo.toml — dependencies                           (tests 55– 65)
 9.  lib.rs — sidecar & tray patterns                    (tests 66– 80)
10.  bundle_backend.ps1 — existence & content            (tests 81– 90)
11.  cortexflow-backend.spec — existence & content       (tests 91– 98)
12.  binaries directory                                   (tests 99–102)
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Repo paths ────────────────────────────────────────────────────────────────

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"
_SRC_TAURI = _FRONTEND / "src-tauri"
_TAURI_CONF = _SRC_TAURI / "tauri.conf.json"
_CAPABILITIES = _SRC_TAURI / "capabilities" / "default.json"
_CARGO_TOML = _SRC_TAURI / "Cargo.toml"
_LIB_RS = _SRC_TAURI / "src" / "lib.rs"
_MAIN_RS = _SRC_TAURI / "src" / "main.rs"
_BUNDLE_SCRIPT = _FRONTEND / "scripts" / "bundle_backend.ps1"
_SPEC_FILE = _REPO / "cortexflow-backend.spec"
_BINARIES_DIR = _SRC_TAURI / "binaries"


# ─────────────────────────────────────────────────────────────────────────────
# 1. desktop_launcher — _default_config_path
# ─────────────────────────────────────────────────────────────────────────────

def test_default_config_path_returns_path() -> None:
    from cortexflow_ai.desktop_launcher import _default_config_path
    p = _default_config_path()
    assert isinstance(p, Path)


def test_default_config_path_under_home() -> None:
    from cortexflow_ai.desktop_launcher import _default_config_path
    p = _default_config_path()
    assert str(p).startswith(str(Path.home()))


def test_default_config_path_ends_with_config_toml() -> None:
    from cortexflow_ai.desktop_launcher import _default_config_path
    p = _default_config_path()
    assert p.name == "config.toml"


def test_default_config_path_parent_is_cortexflow_dir() -> None:
    from cortexflow_ai.desktop_launcher import _default_config_path
    p = _default_config_path()
    assert p.parent.name == ".cortexflow"


# ─────────────────────────────────────────────────────────────────────────────
# 2. desktop_launcher — CORTEXFLOW_PORT override
# ─────────────────────────────────────────────────────────────────────────────

def _run_main_mock_run(env_extras: dict | None = None):
    """Run desktop_launcher.main() with mocked gateway.run and capture the config."""
    captured: list = []

    def fake_run(cfg):
        captured.append(cfg)

    env = {k: v for k, v in os.environ.items()}
    env.pop("CORTEXFLOW_PORT", None)
    if env_extras:
        env.update(env_extras)

    with patch.dict(os.environ, env, clear=True):
        with patch("cortexflow_ai.gateway.main.run", side_effect=fake_run):
            with patch("cortexflow_ai.desktop_launcher._default_config_path",
                       return_value=Path("/nonexistent/path/config.toml")):
                from cortexflow_ai.desktop_launcher import main
                main()
    return captured[0] if captured else None


def test_port_override_applied() -> None:
    cfg = _run_main_mock_run({"CORTEXFLOW_PORT": "9999"})
    assert cfg is not None
    assert cfg.gateway.port == 9999


def test_port_override_zero_is_valid_int() -> None:
    cfg = _run_main_mock_run({"CORTEXFLOW_PORT": "0"})
    assert cfg is not None
    assert cfg.gateway.port == 0


def test_invalid_port_override_is_ignored() -> None:
    cfg = _run_main_mock_run({"CORTEXFLOW_PORT": "not_a_number"})
    assert cfg is not None
    assert cfg.gateway.port != 0  # still uses default


def test_empty_port_env_var_ignored() -> None:
    cfg = _run_main_mock_run({"CORTEXFLOW_PORT": ""})
    assert cfg is not None


def test_no_port_env_uses_config_default() -> None:
    cfg = _run_main_mock_run()
    assert cfg is not None
    from cortexflow_ai.config import CortexFlowConfig
    default_port = CortexFlowConfig().gateway.port
    assert cfg.gateway.port == default_port


def test_port_override_8080() -> None:
    cfg = _run_main_mock_run({"CORTEXFLOW_PORT": "8080"})
    assert cfg.gateway.port == 8080


def test_port_override_1234() -> None:
    cfg = _run_main_mock_run({"CORTEXFLOW_PORT": "1234"})
    assert cfg.gateway.port == 1234


def test_port_override_float_string_ignored() -> None:
    cfg = _run_main_mock_run({"CORTEXFLOW_PORT": "8080.5"})
    assert cfg is not None
    assert cfg.gateway.port != 8080


# ─────────────────────────────────────────────────────────────────────────────
# 3. desktop_launcher — config loading + fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_config_uses_defaults() -> None:
    cfg = _run_main_mock_run()
    assert cfg is not None


def test_config_fallback_gives_cortexflowconfig() -> None:
    from cortexflow_ai.config import CortexFlowConfig
    cfg = _run_main_mock_run()
    assert isinstance(cfg, CortexFlowConfig)


def test_bad_config_path_still_runs() -> None:
    """Even with a broken config path, main() should not raise."""
    cfg = _run_main_mock_run()
    assert cfg is not None


def test_load_config_called_with_none_when_file_missing() -> None:
    """When config file doesn't exist, load_config is called with None."""
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run"):
            with patch("cortexflow_ai.config.load_config") as mock_load:
                mock_load.return_value = MagicMock(gateway=MagicMock(port=7432, bind="127.0.0.1"))
                from cortexflow_ai.desktop_launcher import main
                main()
            mock_load.assert_called_once_with(None)


def test_main_calls_run_with_config() -> None:
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run") as mock_run:
            from cortexflow_ai.desktop_launcher import main
            main()
        mock_run.assert_called_once()


def test_main_run_receives_config_object() -> None:
    from cortexflow_ai.config import CortexFlowConfig
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run") as mock_run:
            from cortexflow_ai.desktop_launcher import main
            main()
        passed_cfg = mock_run.call_args[0][0]
        assert isinstance(passed_cfg, CortexFlowConfig)


def test_exception_in_load_config_falls_back() -> None:
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.config.load_config", side_effect=Exception("bad config")):
            with patch("cortexflow_ai.gateway.main.run"):
                from cortexflow_ai.desktop_launcher import main
                main()  # must not raise


def test_module_is_importable() -> None:
    import importlib
    mod = importlib.import_module("cortexflow_ai.desktop_launcher")
    assert hasattr(mod, "main")


# ─────────────────────────────────────────────────────────────────────────────
# 4. desktop_launcher — SIGTERM handler
# ─────────────────────────────────────────────────────────────────────────────

def test_sigterm_handler_registered() -> None:
    """main() must register a SIGTERM handler before calling run()."""
    registered: list = []

    original_signal = signal.signal

    def capture_signal(sig, handler):
        registered.append((sig, handler))
        return original_signal(sig, handler)

    with patch("signal.signal", side_effect=capture_signal):
        with patch("cortexflow_ai.desktop_launcher._default_config_path",
                   return_value=Path("/no/such/file.toml")):
            with patch("cortexflow_ai.gateway.main.run"):
                from cortexflow_ai.desktop_launcher import main
                main()

    sigterms = [s for s in registered if s[0] == signal.SIGTERM]
    assert len(sigterms) >= 1


def test_sigterm_handler_calls_sys_exit() -> None:
    from cortexflow_ai.desktop_launcher import main

    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run"):
            main()

    # Retrieve the installed SIGTERM handler and verify it exits
    handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit):
        handler(signal.SIGTERM, None)


def test_sigterm_handler_exits_cleanly() -> None:
    from cortexflow_ai.desktop_launcher import main

    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run"):
            main()

    handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit) as exc:
        handler(signal.SIGTERM, None)
    assert exc.value.code == 0


def test_sigterm_handler_is_callable() -> None:
    from cortexflow_ai.desktop_launcher import main

    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run"):
            main()

    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler)


# ─────────────────────────────────────────────────────────────────────────────
# 5. desktop_launcher — gateway startup call
# ─────────────────────────────────────────────────────────────────────────────

def test_gateway_run_called_exactly_once() -> None:
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run") as mock_run:
            from cortexflow_ai.desktop_launcher import main
            main()
        assert mock_run.call_count == 1


def test_gateway_run_called_with_positional_arg() -> None:
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run") as mock_run:
            from cortexflow_ai.desktop_launcher import main
            main()
        args, _ = mock_run.call_args
        assert len(args) == 1  # cfg passed positionally


def test_config_gateway_bind_is_string() -> None:
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run") as mock_run:
            from cortexflow_ai.desktop_launcher import main
            main()
        cfg = mock_run.call_args[0][0]
        assert isinstance(cfg.gateway.bind, str)


def test_config_gateway_port_is_int() -> None:
    with patch("cortexflow_ai.desktop_launcher._default_config_path",
               return_value=Path("/no/such/file.toml")):
        with patch("cortexflow_ai.gateway.main.run") as mock_run:
            from cortexflow_ai.desktop_launcher import main
            main()
        cfg = mock_run.call_args[0][0]
        assert isinstance(cfg.gateway.port, int)


def test_entry_point_function_exists() -> None:
    from cortexflow_ai.desktop_launcher import main
    assert callable(main)


# ─────────────────────────────────────────────────────────────────────────────
# 6. tauri.conf.json — structure & content
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def tauri_conf():
    return json.loads(_TAURI_CONF.read_text(encoding="utf-8"))


def test_tauri_conf_exists() -> None:
    assert _TAURI_CONF.exists(), f"Missing: {_TAURI_CONF}"


def test_tauri_conf_is_valid_json(tauri_conf) -> None:
    assert isinstance(tauri_conf, dict)


def test_tauri_conf_product_name(tauri_conf) -> None:
    assert tauri_conf["productName"] == "CortexFlow-AI"


def test_tauri_conf_identifier(tauri_conf) -> None:
    assert tauri_conf["identifier"] == "ai.cortexflow.desktop"


def test_tauri_conf_version(tauri_conf) -> None:
    assert "version" in tauri_conf


def test_tauri_conf_has_bundle(tauri_conf) -> None:
    assert "bundle" in tauri_conf


def test_tauri_conf_external_bin_present(tauri_conf) -> None:
    assert "externalBin" in tauri_conf["bundle"]


def test_tauri_conf_external_bin_contains_sidecar(tauri_conf) -> None:
    assert "binaries/cortexflow-backend" in tauri_conf["bundle"]["externalBin"]


def test_tauri_conf_before_build_command_references_script(tauri_conf) -> None:
    cmd = tauri_conf.get("build", {}).get("beforeBuildCommand", "")
    assert "bundle_backend.ps1" in cmd


def test_tauri_conf_dev_url(tauri_conf) -> None:
    assert "devUrl" in tauri_conf["build"]


def test_tauri_conf_window_defined(tauri_conf) -> None:
    assert tauri_conf["app"]["windows"]


def test_tauri_conf_window_title(tauri_conf) -> None:
    windows = tauri_conf["app"]["windows"]
    assert any(w.get("title") == "CortexFlow-AI" for w in windows)


def test_tauri_conf_bundle_active(tauri_conf) -> None:
    assert tauri_conf["bundle"]["active"] is True


def test_tauri_conf_icon_list_non_empty(tauri_conf) -> None:
    assert tauri_conf["bundle"]["icon"]


# ─────────────────────────────────────────────────────────────────────────────
# 7. capabilities/default.json — permissions
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cap_conf():
    return json.loads(_CAPABILITIES.read_text(encoding="utf-8"))


def test_capabilities_file_exists() -> None:
    assert _CAPABILITIES.exists(), f"Missing: {_CAPABILITIES}"


def test_capabilities_is_valid_json(cap_conf) -> None:
    assert isinstance(cap_conf, dict)


def test_capabilities_has_permissions(cap_conf) -> None:
    assert "permissions" in cap_conf


def test_capabilities_windows_includes_main(cap_conf) -> None:
    assert "main" in cap_conf.get("windows", [])


def test_capabilities_has_shell_allow_execute(cap_conf) -> None:
    perms = cap_conf["permissions"]
    identifiers = [
        p["identifier"] if isinstance(p, dict) else p
        for p in perms
    ]
    assert "shell:allow-execute" in identifiers


def test_capabilities_sidecar_name_matches(cap_conf) -> None:
    perms = cap_conf["permissions"]
    for p in perms:
        if isinstance(p, dict) and p.get("identifier") == "shell:allow-execute":
            allowed_names = [a["name"] for a in p.get("allow", [])]
            assert "cortexflow-backend" in allowed_names
            return
    pytest.fail("shell:allow-execute permission not found in capabilities")


def test_capabilities_sidecar_flag_set(cap_conf) -> None:
    perms = cap_conf["permissions"]
    for p in perms:
        if isinstance(p, dict) and p.get("identifier") == "shell:allow-execute":
            for entry in p.get("allow", []):
                if entry.get("name") == "cortexflow-backend":
                    assert entry.get("sidecar") is True
                    return
    pytest.fail("sidecar=true not found for cortexflow-backend")


def test_capabilities_has_shell_allow_kill(cap_conf) -> None:
    perms = cap_conf["permissions"]
    identifiers = [
        p["identifier"] if isinstance(p, dict) else p
        for p in perms
    ]
    assert "shell:allow-kill" in identifiers


def test_capabilities_has_core_default(cap_conf) -> None:
    perms = cap_conf["permissions"]
    identifiers = [
        p["identifier"] if isinstance(p, dict) else p
        for p in perms
    ]
    assert "core:default" in identifiers


def test_capabilities_identifier(cap_conf) -> None:
    assert cap_conf.get("identifier") == "default"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Cargo.toml — dependencies
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cargo_text():
    return _CARGO_TOML.read_text(encoding="utf-8")


def test_cargo_toml_exists() -> None:
    assert _CARGO_TOML.exists(), f"Missing: {_CARGO_TOML}"


def test_cargo_toml_has_tauri(cargo_text) -> None:
    assert "tauri" in cargo_text


def test_cargo_toml_has_shell_plugin(cargo_text) -> None:
    assert "tauri-plugin-shell" in cargo_text


def test_cargo_toml_has_single_instance(cargo_text) -> None:
    assert "tauri-plugin-single-instance" in cargo_text


def test_cargo_toml_has_autostart(cargo_text) -> None:
    assert "tauri-plugin-autostart" in cargo_text


def test_cargo_toml_has_global_shortcut(cargo_text) -> None:
    assert "tauri-plugin-global-shortcut" in cargo_text


def test_cargo_toml_has_notification(cargo_text) -> None:
    assert "tauri-plugin-notification" in cargo_text


def test_cargo_toml_edition_2021(cargo_text) -> None:
    assert 'edition = "2021"' in cargo_text


def test_cargo_toml_lib_name(cargo_text) -> None:
    assert 'name = "app_lib"' in cargo_text


def test_cargo_toml_desktop_plugins_cfg_gated(cargo_text) -> None:
    # Desktop-only plugins must be gated behind cfg(not(android/ios))
    assert 'cfg(not(any(target_os = "android"' in cargo_text


def test_cargo_toml_has_log_crate(cargo_text) -> None:
    assert "log" in cargo_text


# ─────────────────────────────────────────────────────────────────────────────
# 9. lib.rs — sidecar & tray patterns
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def lib_rs():
    return _LIB_RS.read_text(encoding="utf-8")


def test_lib_rs_exists() -> None:
    assert _LIB_RS.exists(), f"Missing: {_LIB_RS}"


def test_lib_rs_backend_process_struct(lib_rs) -> None:
    assert "BackendProcess" in lib_rs


def test_lib_rs_sidecar_spawn(lib_rs) -> None:
    assert 'sidecar("cortexflow-backend")' in lib_rs


def test_lib_rs_child_kill_on_exit(lib_rs) -> None:
    assert "child.kill()" in lib_rs


def test_lib_rs_tray_icon_builder(lib_rs) -> None:
    assert "TrayIconBuilder" in lib_rs


def test_lib_rs_set_unread_badge_command(lib_rs) -> None:
    assert "set_unread_badge" in lib_rs


def test_lib_rs_global_shortcut_plugin(lib_rs) -> None:
    assert "tauri_plugin_global_shortcut" in lib_rs


def test_lib_rs_single_instance_plugin(lib_rs) -> None:
    assert "tauri_plugin_single_instance" in lib_rs


def test_lib_rs_autostart_plugin(lib_rs) -> None:
    assert "tauri_plugin_autostart" in lib_rs


def test_lib_rs_prevent_close(lib_rs) -> None:
    assert "prevent_close" in lib_rs


def test_lib_rs_shell_ext_import(lib_rs) -> None:
    assert "ShellExt" in lib_rs


def test_lib_rs_ctrl_shift_space_shortcut(lib_rs) -> None:
    assert "CONTROL" in lib_rs and "SHIFT" in lib_rs and "Space" in lib_rs


def test_lib_rs_hide_on_close(lib_rs) -> None:
    assert "hide()" in lib_rs


def test_lib_rs_manage_backend_process(lib_rs) -> None:
    assert ".manage(BackendProcess" in lib_rs


def test_main_rs_calls_app_lib_run() -> None:
    text = _MAIN_RS.read_text(encoding="utf-8")
    assert "app_lib::run()" in text


# ─────────────────────────────────────────────────────────────────────────────
# 10. bundle_backend.ps1 — existence & content
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def bundle_script():
    return _BUNDLE_SCRIPT.read_text(encoding="utf-8")


def test_bundle_script_exists() -> None:
    assert _BUNDLE_SCRIPT.exists(), f"Missing: {_BUNDLE_SCRIPT}"


def test_bundle_script_is_powershell(bundle_script) -> None:
    assert "param(" in bundle_script or "#" in bundle_script


def test_bundle_script_runs_pyinstaller(bundle_script) -> None:
    assert "PyInstaller" in bundle_script or "pyinstaller" in bundle_script


def test_bundle_script_references_cortexflow_backend(bundle_script) -> None:
    assert "cortexflow-backend" in bundle_script


def test_bundle_script_detects_target_triple(bundle_script) -> None:
    assert "TargetTriple" in bundle_script or "target_triple" in bundle_script.lower()


def test_bundle_script_copies_to_binaries_dir(bundle_script) -> None:
    assert "binaries" in bundle_script.lower()


def test_bundle_script_handles_windows_exe_extension(bundle_script) -> None:
    assert ".exe" in bundle_script


def test_bundle_script_has_python_exe_param(bundle_script) -> None:
    assert "PythonExe" in bundle_script


def test_bundle_script_has_skip_install_flag(bundle_script) -> None:
    assert "SkipInstall" in bundle_script


def test_bundle_script_has_error_handling(bundle_script) -> None:
    assert "ErrorActionPreference" in bundle_script or "exit 1" in bundle_script or "Write-Fail" in bundle_script


# ─────────────────────────────────────────────────────────────────────────────
# 11. cortexflow-backend.spec — existence & content
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def spec_text():
    return _SPEC_FILE.read_text(encoding="utf-8")


def test_spec_file_exists() -> None:
    assert _SPEC_FILE.exists(), f"Missing: {_SPEC_FILE}"


def test_spec_file_has_analysis(spec_text) -> None:
    assert "Analysis(" in spec_text


def test_spec_file_entry_point(spec_text) -> None:
    assert "desktop_launcher.py" in spec_text


def test_spec_file_has_exe(spec_text) -> None:
    assert "EXE(" in spec_text


def test_spec_file_name_is_cortexflow_backend(spec_text) -> None:
    assert 'name="cortexflow-backend"' in spec_text


def test_spec_file_hidden_imports_uvicorn(spec_text) -> None:
    assert "uvicorn" in spec_text


def test_spec_file_hidden_imports_cortexflow(spec_text) -> None:
    assert "cortexflow_ai" in spec_text


def test_spec_file_onefile_console_true(spec_text) -> None:
    assert "console=True" in spec_text


# ─────────────────────────────────────────────────────────────────────────────
# 12. binaries directory
# ─────────────────────────────────────────────────────────────────────────────

def test_binaries_dir_exists() -> None:
    assert _BINARIES_DIR.exists(), f"Missing directory: {_BINARIES_DIR}"


def test_binaries_dir_is_directory() -> None:
    assert _BINARIES_DIR.is_dir()


def test_binaries_dir_has_gitkeep() -> None:
    assert (_BINARIES_DIR / ".gitkeep").exists()


def test_bundle_script_in_scripts_dir() -> None:
    scripts_dir = _FRONTEND / "scripts"
    assert scripts_dir.exists()
    assert _BUNDLE_SCRIPT in list(scripts_dir.iterdir())
