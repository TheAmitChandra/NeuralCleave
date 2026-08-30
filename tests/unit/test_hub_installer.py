"""Unit tests for neuralcleave.hub.installer — HubInstaller."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.hub.installer import HubInstaller, InstallError, ScanBlockedError
from neuralcleave.hub.package import HubPackage
from neuralcleave.hub.registry import HubRegistry
from neuralcleave.hub.scanner import PackageScanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAFE_CODE = "def hello(): return 'hello'"
BLOCKED_CODE = "import subprocess\nsubprocess.run(['rm', '-rf', '/'])"


def make_installer(tmp_path, *, skill_writer=None, plugin_registry=None) -> HubInstaller:
    """Defaults to a tmp_path-isolated SkillWriter so tests never touch the
    real ~/.neuralcleave/skills/ directory now that HubInstaller.__init__
    auto-constructs a real SkillWriter whenever one isn't given."""
    from neuralcleave.skills.writer import SkillWriter

    registry = HubRegistry(registry_file=tmp_path / "reg.json")
    if skill_writer is None and plugin_registry is None:
        skill_writer = SkillWriter(skills_dir=tmp_path / "skills")
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


@pytest.mark.asyncio
async def test_fetch_code_rejects_cleartext_http():
    """Round 7 gap analysis 5.3 (2026-08-30): cleartext http:// was
    accepted despite this method's own documented https-only contract -
    fetched code gets loaded and registered as a live, LLM-callable tool,
    so an unencrypted fetch let a network-position attacker substitute
    what actually runs."""
    installer = HubInstaller.__new__(HubInstaller)
    with pytest.raises(InstallError, match="Unsupported URL scheme"):
        await installer._fetch_code("http://example.com/skill.py")


# ---------------------------------------------------------------------------
# scan_url — removed (round 7 gap analysis 5.3, 2026-08-30): zero callers
# anywhere in the repo, and its asyncio.get_event_loop().run_until_complete()
# implementation would raise if ever called from an async context.
# ---------------------------------------------------------------------------


def test_scan_url_no_longer_exists():
    assert not hasattr(HubInstaller, "scan_url")


# ---------------------------------------------------------------------------
# __init__ — auto-constructs a SkillWriter when none given
# ---------------------------------------------------------------------------


def test_no_skill_writer_or_registry_constructs_a_bare_skill_writer(tmp_path):
    from neuralcleave.skills.writer import SkillWriter

    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", tmp_path / "skills"):
        installer = HubInstaller(
            hub_dir=tmp_path / "hub",
            registry=HubRegistry(registry_file=tmp_path / "reg.json"),
        )

    assert isinstance(installer._skill_writer, SkillWriter)
    assert installer._skill_writer._registry is None


def test_plugin_registry_without_a_skill_writer_still_reaches_the_writer(tmp_path):
    """Regression guard: this is the exact bug found in the round 5 gap
    analysis (2026-08-21 P1) - gateway/main.py passes plugin_registry=...
    but not skill_writer=..., and that reference was previously stored and
    never read anywhere, so hub installs never became callable tools."""
    fake_plugin_registry = MagicMock()

    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", tmp_path / "skills"):
        installer = HubInstaller(
            hub_dir=tmp_path / "hub",
            registry=HubRegistry(registry_file=tmp_path / "reg.json"),
            plugin_registry=fake_plugin_registry,
        )

    assert installer._skill_writer._registry is fake_plugin_registry


def test_explicit_skill_writer_is_not_overridden(tmp_path):
    sw = MagicMock()
    installer = HubInstaller(
        hub_dir=tmp_path / "hub",
        registry=HubRegistry(registry_file=tmp_path / "reg.json"),
        skill_writer=sw,
        plugin_registry=MagicMock(),
    )
    assert installer._skill_writer is sw


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


# ---------------------------------------------------------------------------
# install — expected_checksum verification (round 7 gap analysis 5.3,
# 2026-08-30): the recorded checksum used to only ever document what was
# fetched, it never verified it against a publisher-declared digest.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_matching_checksum_succeeds(tmp_path):
    import hashlib
    installer = make_installer(tmp_path)
    correct = hashlib.sha256(SAFE_CODE.encode()).hexdigest()
    pkg = await installer.install(
        data_uri(SAFE_CODE), name="verified-skill", expected_checksum=correct
    )
    assert pkg.checksum == correct


@pytest.mark.asyncio
async def test_install_matching_checksum_is_case_insensitive(tmp_path):
    import hashlib
    installer = make_installer(tmp_path)
    correct_upper = hashlib.sha256(SAFE_CODE.encode()).hexdigest().upper()
    pkg = await installer.install(
        data_uri(SAFE_CODE), name="verified-skill-2", expected_checksum=correct_upper
    )
    assert pkg is not None


@pytest.mark.asyncio
async def test_install_mismatched_checksum_raises_before_writing_anything(tmp_path):
    installer = make_installer(tmp_path)
    with pytest.raises(InstallError, match="Checksum mismatch"):
        await installer.install(
            data_uri(SAFE_CODE), name="tampered-skill",
            expected_checksum="0" * 64,
        )
    # Nothing should have been registered or written to disk.
    assert installer._registry.get("tampered-skill") is None


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
async def test_install_scanner_blocked_but_skillwriter_clean_succeeds_with_force(tmp_path):
    """force=True overrides the Hub's own PackageScanner (a heuristic
    regex/pattern scan) for code that SkillWriter's independent
    blocked-import check doesn't also flag."""
    scanner_only_blocked_code = "import os\nos.system('echo hi')"  # os isn't AST-blocked by SkillWriter
    installer = make_installer(tmp_path)
    pkg = await installer.install(data_uri(scanner_only_blocked_code), name="forced-danger", force=True)
    assert pkg.name == "forced-danger"


@pytest.mark.asyncio
async def test_install_force_does_not_bypass_skillwriters_own_blocked_import_check(tmp_path):
    """Regression guard: force=True must only override the scanner.
    SkillWriter's own blocked-import check (subprocess, ctypes, etc.) has
    no override anywhere else in the codebase (agent-authored skills can't
    bypass it via review approval either) - a Hub install forcing past a
    scanner warning shouldn't get a weaker guarantee than every other path
    that writes a skill."""
    installer = make_installer(tmp_path)
    with pytest.raises(InstallError, match="Blocked import"):
        await installer.install(data_uri(BLOCKED_CODE), name="still-blocked", force=True)


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
async def test_install_with_no_skill_writer_given_still_writes_and_loads(tmp_path):
    """Round 5 gap analysis P1 (2026-08-21): before this, omitting
    skill_writer fell into a raw-file-write path with zero validation and
    no registration at all. Now it goes through a real, auto-constructed
    SkillWriter's write_skill() (validated, loaded, hot-reload-eligible)."""
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", tmp_path / "skills"):
        installer = HubInstaller(
            hub_dir=tmp_path / "hub",
            registry=HubRegistry(registry_file=tmp_path / "reg.json"),
        )
        await installer.install(data_uri(SAFE_CODE), name="direct_skill")

    skill_path = tmp_path / "skills" / "direct_skill" / "skill.py"
    assert skill_path.exists()
    assert "direct_skill" in installer._skill_writer._loaded_skills


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
