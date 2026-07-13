"""Tests for cortexflow_ai/sandbox/ — SandboxResult, Sandbox ABC,
LocalSandbox, DockerSandbox, SSHSandbox, SandboxManager, and the CLI.

All Docker and SSH tests mock the subprocess/asyncssh layer so the suite
runs without Docker or a live SSH server.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from cortexflow_ai.sandbox.base import Sandbox, SandboxResult
from cortexflow_ai.sandbox.docker import DockerSandbox
from cortexflow_ai.sandbox.local import LocalSandbox, _sanitise_env
from cortexflow_ai.sandbox.manager import SandboxManager
from cortexflow_ai.sandbox.ssh import SSHSandbox, shlex_quote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_result(backend: str = "local") -> SandboxResult:
    return SandboxResult(stdout="ok", stderr="", exit_code=0, backend=backend)


def _err_result(backend: str = "local") -> SandboxResult:
    return SandboxResult(stdout="", stderr="boom", exit_code=1, backend=backend)


def _make_proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# SandboxResult
# ---------------------------------------------------------------------------


def test_result_success_zero_exit() -> None:
    r = SandboxResult(stdout="hi", stderr="", exit_code=0, backend="local")
    assert r.success is True


def test_result_failure_nonzero_exit() -> None:
    r = SandboxResult(stdout="", stderr="err", exit_code=1, backend="local")
    assert r.success is False


def test_result_timed_out_not_success() -> None:
    r = SandboxResult(stdout="", stderr="", exit_code=0, timed_out=True, backend="local")
    assert r.success is False


def test_result_to_dict_keys() -> None:
    r = SandboxResult(stdout="x", stderr="", exit_code=0, backend="local")
    d = r.to_dict()
    assert set(d.keys()) == {"stdout", "stderr", "exit_code", "timed_out", "backend", "success"}


def test_result_to_dict_values() -> None:
    r = SandboxResult(stdout="out", stderr="err", exit_code=2, timed_out=False, backend="docker")
    d = r.to_dict()
    assert d["stdout"] == "out"
    assert d["exit_code"] == 2
    assert d["backend"] == "docker"
    assert d["success"] is False


def test_result_metadata_default_empty() -> None:
    r = SandboxResult(stdout="", stderr="", exit_code=0, backend="local")
    assert r.metadata == {}


def test_result_metadata_stored() -> None:
    r = SandboxResult(stdout="", stderr="", exit_code=0, backend="docker",
                      metadata={"image": "python:3.12"})
    assert r.metadata["image"] == "python:3.12"


# ---------------------------------------------------------------------------
# _sanitise_env (LocalSandbox helper)
# ---------------------------------------------------------------------------


def test_sanitise_env_strips_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    clean = _sanitise_env(None)
    assert "ANTHROPIC_API_KEY" not in clean


def test_sanitise_env_strips_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-xxx")
    clean = _sanitise_env(None)
    assert "OPENAI_API_KEY" not in clean


def test_sanitise_env_keeps_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    clean = _sanitise_env(None)
    assert "PATH" in clean


def test_sanitise_env_merges_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    clean = _sanitise_env({"MY_VAR": "hello"})
    assert clean["MY_VAR"] == "hello"


def test_sanitise_env_extra_overrides_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_VAR", "host_val")
    clean = _sanitise_env({"MY_VAR": "override"})
    assert clean["MY_VAR"] == "override"


def test_sanitise_env_strips_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    clean = _sanitise_env(None)
    assert "GEMINI_API_KEY" not in clean


def test_sanitise_env_strips_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    clean = _sanitise_env(None)
    assert "DEEPSEEK_API_KEY" not in clean


# ---------------------------------------------------------------------------
# LocalSandbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_execute_success(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell", return_value=_make_proc(b"hello\n", b"")):
        result = await sb.execute("echo hello")
    assert result.success
    assert "hello" in result.stdout
    assert result.backend == "local"


@pytest.mark.asyncio
async def test_local_execute_nonzero_exit(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell", return_value=_make_proc(b"", b"err", 1)):
        result = await sb.execute("false")
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_local_execute_timeout(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path, default_timeout=0.01)

    proc = AsyncMock()
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_shell", return_value=proc):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await sb.execute("sleep 10")
    assert result.timed_out
    assert not result.success
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_local_execute_spawn_error(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell", side_effect=OSError("no shell")):
        result = await sb.execute("anything")
    assert not result.success
    assert "no shell" in result.stderr


@pytest.mark.asyncio
async def test_local_execute_caps_output(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path, max_output_bytes=5)
    big = b"A" * 100
    with patch("asyncio.create_subprocess_shell", return_value=_make_proc(big, b"")):
        result = await sb.execute("cat big")
    assert len(result.stdout) == 5


@pytest.mark.asyncio
async def test_local_execute_stderr_captured(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell", return_value=_make_proc(b"", b"error msg")):
        result = await sb.execute("badcmd")
    assert "error msg" in result.stderr


@pytest.mark.asyncio
async def test_local_ping_success(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell",
               return_value=_make_proc(b"__sandbox_ok__\n", b"")):
        assert await sb.ping() is True


@pytest.mark.asyncio
async def test_local_ping_failure(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell", return_value=_make_proc(b"", b"err", 1)):
        assert await sb.ping() is False


def test_local_info_keys(tmp_path: Path) -> None:
    sb = LocalSandbox(work_dir=tmp_path)
    info = sb.info()
    assert info["backend"] == "local"
    assert "work_dir" in info
    assert "default_timeout" in info


def test_local_backend_name() -> None:
    assert LocalSandbox().backend_name == "local"


def test_local_creates_work_dir(tmp_path: Path) -> None:
    work = tmp_path / "new_dir"
    sb = LocalSandbox(work_dir=work)

    async def _run():
        with patch("asyncio.create_subprocess_shell", return_value=_make_proc(b"x", b"")):
            await sb.execute("echo x")

    asyncio.run(_run())
    assert work.exists()


# ---------------------------------------------------------------------------
# DockerSandbox
# ---------------------------------------------------------------------------


def _docker_proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


@pytest.mark.asyncio
async def test_docker_execute_no_docker(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    with patch("shutil.which", return_value=None):
        result = await sb.execute("echo hi")
    assert not result.success
    assert "docker" in result.stderr.lower()


@pytest.mark.asyncio
async def test_docker_execute_success(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("asyncio.create_subprocess_exec",
                   return_value=_docker_proc(b"hello\n", b"")):
            result = await sb.execute("echo hello")
    assert result.success
    assert "hello" in result.stdout
    assert result.backend == "docker"


@pytest.mark.asyncio
async def test_docker_execute_nonzero(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("asyncio.create_subprocess_exec",
                   return_value=_docker_proc(b"", b"fail", 1)):
            result = await sb.execute("false")
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_docker_execute_timeout(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path, default_timeout=0.01)
    with patch("shutil.which", return_value="/usr/bin/docker"):
        proc = AsyncMock()
        proc.kill = MagicMock()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await sb.execute("sleep 60")
    assert result.timed_out
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_docker_execute_spawn_error(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("nope")):
            result = await sb.execute("echo x")
    assert not result.success
    assert "nope" in result.stderr


@pytest.mark.asyncio
async def test_docker_execute_caps_output(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path, max_output_bytes=3)
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("asyncio.create_subprocess_exec",
                   return_value=_docker_proc(b"ABCDEFGH", b"")):
            result = await sb.execute("cat")
    assert len(result.stdout) == 3


def test_docker_build_command_basics(tmp_path: Path) -> None:
    sb = DockerSandbox(image="alpine", network="none", memory="128m",
                       cpus=0.25, work_dir=tmp_path)
    cmd = sb._build_command("echo hi", None, None)
    assert "docker" in cmd
    assert "run" in cmd
    assert "--rm" in cmd
    assert "alpine" in cmd
    assert "echo hi" in cmd
    assert "--network" in cmd
    assert "none" in cmd


def test_docker_build_command_env(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    cmd = sb._build_command("env", {"FOO": "bar"}, None)
    assert "-e" in cmd
    assert "FOO=bar" in cmd


def test_docker_build_command_cwd(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    cmd = sb._build_command("ls", None, "/tmp")
    assert "-w" in cmd
    assert "/tmp" in cmd


def test_docker_build_command_extra_flags(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path, extra_flags=["--read-only"])
    cmd = sb._build_command("ls", None, None)
    assert "--read-only" in cmd


def test_docker_build_command_security_opt(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    cmd = sb._build_command("id", None, None)
    assert "--security-opt" in cmd
    assert "no-new-privileges" in cmd


@pytest.mark.asyncio
async def test_docker_ping_no_docker() -> None:
    sb = DockerSandbox()
    with patch("shutil.which", return_value=None):
        assert await sb.ping() is False


@pytest.mark.asyncio
async def test_docker_ping_success() -> None:
    sb = DockerSandbox()
    with patch("shutil.which", return_value="/usr/bin/docker"):
        proc = AsyncMock()
        proc.wait = AsyncMock(return_value=None)
        proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await sb.ping() is True


@pytest.mark.asyncio
async def test_docker_ping_failure() -> None:
    sb = DockerSandbox()
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("asyncio.create_subprocess_exec", side_effect=OSError("no daemon")):
            assert await sb.ping() is False


def test_docker_info_keys(tmp_path: Path) -> None:
    sb = DockerSandbox(work_dir=tmp_path)
    info = sb.info()
    assert info["backend"] == "docker"
    assert "image" in info
    assert "network" in info
    assert "memory" in info


def test_docker_metadata_in_result(tmp_path: Path) -> None:
    async def _run():
        sb = DockerSandbox(image="alpine", work_dir=tmp_path)
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("asyncio.create_subprocess_exec",
                       return_value=_docker_proc(b"x", b"")):
                return await sb.execute("echo x")

    result = asyncio.run(_run())
    assert result.metadata.get("image") == "alpine"


def test_docker_backend_name() -> None:
    assert DockerSandbox().backend_name == "docker"


# ---------------------------------------------------------------------------
# SSHSandbox — shlex_quote
# ---------------------------------------------------------------------------


def test_shlex_quote_simple() -> None:
    assert shlex_quote("hello") == "'hello'"


def test_shlex_quote_with_spaces() -> None:
    q = shlex_quote("hello world")
    assert " " in q
    assert q.startswith("'")


def test_shlex_quote_with_single_quote() -> None:
    q = shlex_quote("it's")
    assert "'" in q


# ---------------------------------------------------------------------------
# SSHSandbox — _wrap_command
# ---------------------------------------------------------------------------


def test_ssh_wrap_command_plain() -> None:
    sb = SSHSandbox(host="host")
    assert sb._wrap_command("ls", None, None) == "ls"


def test_ssh_wrap_command_with_env() -> None:
    sb = SSHSandbox(host="host")
    wrapped = sb._wrap_command("ls", {"FOO": "bar"}, None)
    assert "FOO" in wrapped
    assert "export" in wrapped


def test_ssh_wrap_command_with_cwd() -> None:
    sb = SSHSandbox(host="host")
    wrapped = sb._wrap_command("ls", None, "/tmp")
    assert "cd" in wrapped
    assert "/tmp" in wrapped


def test_ssh_wrap_command_env_and_cwd() -> None:
    sb = SSHSandbox(host="host")
    wrapped = sb._wrap_command("ls", {"X": "1"}, "/tmp")
    assert "export" in wrapped
    assert "cd" in wrapped


# ---------------------------------------------------------------------------
# SSHSandbox — _build_cli_args
# ---------------------------------------------------------------------------


def test_ssh_build_cli_args_basic() -> None:
    sb = SSHSandbox(host="myhost", port=22)
    args = sb._build_cli_args()
    assert "ssh" in args
    assert "-p" in args
    assert "22" in args


def test_ssh_build_cli_args_no_known_hosts() -> None:
    sb = SSHSandbox(host="myhost", known_hosts=None)
    args = sb._build_cli_args()
    assert "StrictHostKeyChecking=no" in " ".join(args)


def test_ssh_build_cli_args_known_hosts_file() -> None:
    sb = SSHSandbox(host="myhost", known_hosts="/tmp/kh")
    args = sb._build_cli_args()
    assert "/tmp/kh" in " ".join(args)


def test_ssh_build_cli_args_key_path() -> None:
    sb = SSHSandbox(host="h", key_path="/home/user/.ssh/id_ed25519")
    args = sb._build_cli_args()
    assert "-i" in args
    assert str(Path("/home/user/.ssh/id_ed25519")) in args


def test_ssh_build_cli_args_username() -> None:
    sb = SSHSandbox(host="h", username="ci")
    args = sb._build_cli_args()
    assert "-l" in args
    assert "ci" in args


# ---------------------------------------------------------------------------
# SSHSandbox — execute via CLI fallback (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_execute_cli_success() -> None:
    sb = SSHSandbox(host="myhost", known_hosts=None)
    with patch("shutil.which", return_value="/usr/bin/ssh"):
        proc = _make_proc(b"hi\n", b"", 0)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            # Force asyncssh ImportError so we fall back to CLI
            with patch.dict(sys.modules, {"asyncssh": None}):
                result = await sb.execute("echo hi")
    assert result.backend == "ssh"
    # We just verify no exception and an exit code was set
    assert isinstance(result.exit_code, int)


@pytest.mark.asyncio
async def test_ssh_execute_no_ssh_cli_no_asyncssh() -> None:
    sb = SSHSandbox(host="myhost")
    with patch("shutil.which", return_value=None):
        with patch.dict(sys.modules, {"asyncssh": None}):
            result = await sb.execute("echo hi")
    assert not result.success


@pytest.mark.asyncio
async def test_ssh_execute_timeout() -> None:
    sb = SSHSandbox(host="myhost", default_timeout=0.01)
    with patch("shutil.which", return_value="/usr/bin/ssh"):
        with patch.dict(sys.modules, {"asyncssh": None}):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await sb.execute("sleep 60")
    assert result.timed_out


def test_ssh_info_keys() -> None:
    sb = SSHSandbox(host="h", port=2222, username="user")
    info = sb.info()
    assert info["backend"] == "ssh"
    assert info["host"] == "h"
    assert info["port"] == 2222


def test_ssh_backend_name() -> None:
    assert SSHSandbox(host="h").backend_name == "ssh"


# ---------------------------------------------------------------------------
# SandboxManager — factory methods
# ---------------------------------------------------------------------------


def test_manager_local_factory() -> None:
    mgr = SandboxManager.local()
    assert mgr.backend == "local"
    assert isinstance(mgr.sandbox, LocalSandbox)


def test_manager_docker_factory() -> None:
    mgr = SandboxManager.docker(image="alpine")
    assert mgr.backend == "docker"
    assert isinstance(mgr.sandbox, DockerSandbox)


def test_manager_ssh_factory() -> None:
    mgr = SandboxManager.ssh(host="myhost")
    assert mgr.backend == "ssh"
    assert isinstance(mgr.sandbox, SSHSandbox)


def test_manager_from_config_local() -> None:
    mgr = SandboxManager.from_config({"backend": "local"})
    assert mgr.backend == "local"


def test_manager_from_config_docker() -> None:
    mgr = SandboxManager.from_config({"backend": "docker", "image": "alpine"})
    assert mgr.backend == "docker"


def test_manager_from_config_ssh() -> None:
    mgr = SandboxManager.from_config({"backend": "ssh", "host": "myhost"})
    assert mgr.backend == "ssh"


def test_manager_from_config_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown sandbox backend"):
        SandboxManager.from_config({"backend": "magic"})


def test_manager_from_config_ssh_no_host_raises() -> None:
    with pytest.raises(ValueError, match="host"):
        SandboxManager.from_config({"backend": "ssh"})


def test_manager_from_config_default_local() -> None:
    mgr = SandboxManager.from_config({})
    assert mgr.backend == "local"


def test_manager_info_delegates() -> None:
    mgr = SandboxManager.local()
    info = mgr.info()
    assert info["backend"] == "local"


@pytest.mark.asyncio
async def test_manager_execute_delegates(tmp_path: Path) -> None:
    mgr = SandboxManager.local(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell",
               return_value=_make_proc(b"hi\n", b"")):
        result = await mgr.execute("echo hi")
    assert result.success


@pytest.mark.asyncio
async def test_manager_ping_delegates_true(tmp_path: Path) -> None:
    mgr = SandboxManager.local(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell",
               return_value=_make_proc(b"__sandbox_ok__\n", b"")):
        assert await mgr.ping() is True


@pytest.mark.asyncio
async def test_manager_ping_delegates_false(tmp_path: Path) -> None:
    mgr = SandboxManager.local(work_dir=tmp_path)
    with patch("asyncio.create_subprocess_shell",
               return_value=_make_proc(b"", b"", 1)):
        assert await mgr.ping() is False


def test_manager_backend_property() -> None:
    mgr = SandboxManager.docker()
    assert mgr.backend == "docker"


def test_manager_sandbox_property() -> None:
    sb = LocalSandbox()
    mgr = SandboxManager(sb)
    assert mgr.sandbox is sb


# ---------------------------------------------------------------------------
# Sandbox ABC
# ---------------------------------------------------------------------------


def test_sandbox_is_abstract() -> None:
    with pytest.raises(TypeError):
        Sandbox()  # type: ignore[abstract]


def test_sandbox_info_default() -> None:
    class MinSandbox(Sandbox):
        backend_name = "min"

        async def execute(self, command, **kwargs):
            return _ok_result("min")

        async def ping(self) -> bool:
            return True

    sb = MinSandbox()
    assert sb.info() == {"backend": "min"}


# ---------------------------------------------------------------------------
# CLI — cortex sandbox status / test
# ---------------------------------------------------------------------------

from cortexflow_ai.cli import cli  # noqa: E402


def test_cli_sandbox_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["sandbox", "--help"], obj={})
    assert result.exit_code == 0
    assert "status" in result.output
    assert "test" in result.output


def test_cli_sandbox_status_local(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch("cortexflow_ai.sandbox.local.LocalSandbox.ping", new=AsyncMock(return_value=True)):
        result = runner.invoke(cli, ["sandbox", "status", "--backend", "local"], obj={})
    assert result.exit_code == 0
    assert "local" in result.output.lower()


def test_cli_sandbox_status_docker(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch("cortexflow_ai.sandbox.docker.DockerSandbox.ping", new=AsyncMock(return_value=False)):
        result = runner.invoke(cli, ["sandbox", "status", "--backend", "docker"], obj={})
    assert result.exit_code == 0


def test_cli_sandbox_status_ssh_no_host() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["sandbox", "status", "--backend", "ssh"], obj={})
    assert result.exit_code != 0
    assert "host" in result.output.lower()


def test_cli_sandbox_test_local_success(tmp_path: Path) -> None:
    runner = CliRunner()
    ok = SandboxResult(stdout="sandbox ok\n", stderr="", exit_code=0, backend="local")
    with patch("cortexflow_ai.sandbox.local.LocalSandbox.execute", new=AsyncMock(return_value=ok)):
        result = runner.invoke(
            cli, ["sandbox", "test", "--backend", "local", "--command", "echo hi"],
            obj={},
        )
    assert result.exit_code == 0


def test_cli_sandbox_test_local_failure(tmp_path: Path) -> None:
    runner = CliRunner()
    fail = SandboxResult(stdout="", stderr="oops", exit_code=1, backend="local")
    with patch("cortexflow_ai.sandbox.local.LocalSandbox.execute", new=AsyncMock(return_value=fail)):
        result = runner.invoke(
            cli, ["sandbox", "test", "--backend", "local", "--command", "false"],
            obj={},
        )
    assert result.exit_code != 0


def test_cli_sandbox_test_ssh_no_host() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["sandbox", "test", "--backend", "ssh"], obj={}
    )
    assert result.exit_code != 0
    assert "host" in result.output.lower()


def test_cli_sandbox_test_docker(tmp_path: Path) -> None:
    runner = CliRunner()
    ok = SandboxResult(stdout="hi\n", stderr="", exit_code=0, backend="docker")
    with patch("cortexflow_ai.sandbox.docker.DockerSandbox.execute", new=AsyncMock(return_value=ok)):
        result = runner.invoke(
            cli, ["sandbox", "test", "--backend", "docker", "--command", "echo hi"],
            obj={},
        )
    assert result.exit_code == 0
