"""Unit tests for cortexflow_ai.hub.installer — HubInstaller."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.hub.installer import HubInstaller, InstallError, ScanBlockedError
from cortexflow_ai.hub.package import HubPackage
from cortexflow_ai.hub.registry import HubRegistry
from cortexflow_ai.hub.scanner import PackageScanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAFE_CODE = "def hello(): return 'hello'"
BLOCKED_CODE = "import subprocess\nsubprocess.run(['rm', '-rf', '/'])"


def make_installer(tmp_path, *, skill_writer=None, plugin_registry=None) -> HubInstaller:
    registry = HubRegistry(registry_file=tmp_path / "reg.json")
    return HubInstaller(
        hub_dir=tmp_path / "hub",
        registry=registry,
        skill_writer=skill_writer,
        plugin_registry=plugin_registry,
    )


def data_uri(code: str) -> str:
    return f"data:text/plain,{code}"


# ---------------------------------------------------------------------------
# _resolve_name
# ---------------------------------------------------------------------------


def test_resolve_name_from_url():
    name = HubInstaller._resolve_name(None, "https://example.com/my-skill.py")
    assert name == "my_skill"


def test_resolve_name_explicit():
    name = HubInstaller._resolve_name("custom", "https://example.com/other.py")
    assert name == "custom"


def test_resolve_name_root_url_uses_domain_stem():
    # Domain "example.com" → PurePosixPath stem "example"
    name = HubInstaller._resolve_name(None, "https://example.com/")
    assert name == "example"


def test_resolve_name_sanitises_special_chars():
    name = HubInstaller._resolve_name(None, "https://example.com/my.cool-skill.py")
    assert name == "my_cool_skill"


# ---------------------------------------------------------------------------
# _decode_data_uri
# ---------------------------------------------------------------------------


def test_decode_data_uri_plain():
    uri = "data:text/plain,hello%20world"
    assert HubInstaller._decode_data_uri(uri) == "hello world"


def test_decode_data_uri_base64():
    encoded = base64.b64encode(b"def hi(): pass").decode()
    uri = f"data:text/plain;base64,{encoded}"
    assert HubInstaller._decode_data_uri(uri) == "def hi(): pass"


# ---------------------------------------------------------------------------
# _fetch_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_code_data_uri():
    installer = HubInstaller.__new__(HubInstaller)
    installer._scanner = PackageScanner()
    code = await installer._fetch_code("data:text/plain,def foo(): pass")
    assert "def foo" in code


@pytest.mark.asyncio
async def test_fetch_code_unsupported_scheme():
    installer = HubInstaller.__new__(HubInstaller)
    with pytest.raises(InstallError, match="Unsupported URL scheme"):
        await installer._fetch_code("ftp://example.com/skill.py")


@pytest.mark.asyncio
async def test_fetch_code_https_success():
    installer = HubInstaller.__new__(HubInstaller)
    mock_resp = MagicMock()
    mock_resp.text = SAFE_CODE
    mock_resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        code = await installer._fetch_code("https://example.com/skill.py")
    assert code == SAFE_CODE


@pytest.mark.asyncio
async def test_fetch_code_https_error_raises_install_error():
    installer = HubInstaller.__new__(HubInstaller)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(InstallError, match="Failed to fetch"):
            await installer._fetch_code("https://bad.example.com/skill.py")


# ---------------------------------------------------------------------------
# install — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_data_uri_returns_package(tmp_path):
    installer = make_installer(tmp_path)
    uri = data_uri(SAFE_CODE)
    pkg = await installer.install(uri, name="hello-skill", description="greet")
    assert isinstance(pkg, HubPackage)
    assert pkg.name == "hello-skill"
    assert pkg.description == "greet"
    assert pkg.checksum != ""


@pytest.mark.asyncio
async def test_install_registers_package(tmp_path):
    installer = make_installer(tmp_path)
    await installer.install(data_uri(SAFE_CODE), name="reg-skill")
    assert installer._registry.get("reg-skill") is not None


@pytest.mark.asyncio
async def test_install_sets_checksum(tmp_path):
    import hashlib
    installer = make_installer(tmp_path)
    pkg = await installer.install(data_uri(SAFE_CODE), name="chk-skill")
    expected = hashlib.sha256(SAFE_CODE.encode()).hexdigest()
    assert pkg.checksum == expected


@pytest.mark.asyncio
async def test_install_with_tags(tmp_path):
    installer = make_installer(tmp_path)
    pkg = await installer.install(data_uri(SAFE_CODE), name="tagged", tags=["a", "b"])
    assert pkg.tags == ["a", "b"]


@pytest.mark.asyncio
async def test_install_infers_name_from_url(tmp_path):
    installer = make_installer(tmp_path)
    pkg = await installer.install(data_uri(SAFE_CODE))
    assert pkg.name != ""


# ---------------------------------------------------------------------------
# install — duplicate blocked unless force
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_duplicate_raises_install_error(tmp_path):
    installer = make_installer(tmp_path)
    await installer.install(data_uri(SAFE_CODE), name="dup-skill")
    with pytest.raises(InstallError, match="already installed"):
        await installer.install(data_uri(SAFE_CODE), name="dup-skill")


@pytest.mark.asyncio
async def test_install_duplicate_force_succeeds(tmp_path):
    installer = make_installer(tmp_path)
    await installer.install(data_uri(SAFE_CODE), name="dup2")
    pkg = await installer.install(data_uri(SAFE_CODE), name="dup2", force=True)
    assert pkg.name == "dup2"


# ---------------------------------------------------------------------------
# install — scanner blocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_blocked_code_raises_scan_blocked(tmp_path):
    installer = make_installer(tmp_path)
    with pytest.raises(ScanBlockedError):
        await installer.install(data_uri(BLOCKED_CODE), name="danger")


@pytest.mark.asyncio
async def test_install_blocked_code_force_succeeds(tmp_path):
    installer = make_installer(tmp_path)
    pkg = await installer.install(data_uri(BLOCKED_CODE), name="forced-danger", force=True)
    assert pkg.name == "forced-danger"


# ---------------------------------------------------------------------------
# install — skill_writer integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_calls_skill_writer(tmp_path):
    sw = MagicMock()
    installer = make_installer(tmp_path, skill_writer=sw)
    await installer.install(data_uri(SAFE_CODE), name="sw-skill", description="desc")
    sw.write_skill.assert_called_once_with("sw-skill", SAFE_CODE, "desc")


@pytest.mark.asyncio
async def test_install_skill_writer_error_raises_install_error(tmp_path):
    sw = MagicMock()
    sw.write_skill.side_effect = Exception("disk full")
    installer = make_installer(tmp_path, skill_writer=sw)
    with pytest.raises(InstallError, match="SkillWriter failed"):
        await installer.install(data_uri(SAFE_CODE), name="sw-err")


@pytest.mark.asyncio
async def test_install_no_skill_writer_writes_direct(tmp_path):
    installer = make_installer(tmp_path)
    await installer.install(data_uri(SAFE_CODE), name="direct-skill")
    skill_path = Path.home() / ".cortexflow" / "skills" / "direct-skill" / "skill.py"
    assert skill_path.exists()


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uninstall_removes_from_registry(tmp_path):
    installer = make_installer(tmp_path)
    await installer.install(data_uri(SAFE_CODE), name="rm-me")
    installer.uninstall("rm-me")
    assert installer._registry.get("rm-me") is None


def test_uninstall_missing_raises(tmp_path):
    installer = make_installer(tmp_path)
    with pytest.raises(InstallError, match="No hub package"):
        installer.uninstall("ghost")


@pytest.mark.asyncio
async def test_uninstall_calls_skill_writer(tmp_path):
    sw = MagicMock()
    installer = make_installer(tmp_path, skill_writer=sw)
    await installer.install(data_uri(SAFE_CODE), name="del-me")
    installer.uninstall("del-me")
    sw.delete_skill.assert_called_once_with("del-me")


@pytest.mark.asyncio
async def test_uninstall_skill_writer_error_logged_not_raised(tmp_path):
    sw = MagicMock()
    sw.delete_skill.side_effect = Exception("already gone")
    installer = make_installer(tmp_path, skill_writer=sw)
    await installer.install(data_uri(SAFE_CODE), name="forgive-me")
    installer.uninstall("forgive-me")
    assert installer._registry.get("forgive-me") is None
