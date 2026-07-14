"""Unit tests for hub marketplace REST endpoints — /api/v1/hub/..."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import cortexflow_ai.gateway.routes as routes_module
from cortexflow_ai.gateway.routes import router
from cortexflow_ai.hub.installer import InstallError, ScanBlockedError
from cortexflow_ai.hub.package import HubPackage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def make_pkg(name: str = "test-skill", enabled: bool = True) -> HubPackage:
    return HubPackage(
        name=name,
        version="1.0.0",
        description="A test skill",
        author="Alice",
        source_url="https://example.com/test.py",
        install_date="2026-07-14T00:00:00Z",
        enabled=enabled,
    )


def mock_installer(packages: list[HubPackage] | None = None) -> MagicMock:
    packages = packages or []
    inst = MagicMock()
    inst._registry = MagicMock()
    inst._registry.list_packages.return_value = packages
    inst._registry.package_count.return_value = len(packages)
    inst._registry.get.return_value = packages[0] if packages else None
    inst._registry.search.return_value = packages
    return inst


# ---------------------------------------------------------------------------
# GET /api/v1/hub/status
# ---------------------------------------------------------------------------


def test_hub_status_no_installer(client):
    routes_module.set_hub_installer(None)
    resp = client.get("/api/v1/hub/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["package_count"] == 0


def test_hub_status_with_installer(client):
    inst = mock_installer([make_pkg()])
    routes_module.set_hub_installer(inst)
    resp = client.get("/api/v1/hub/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["package_count"] == 1


# ---------------------------------------------------------------------------
# GET /api/v1/hub/packages
# ---------------------------------------------------------------------------


def test_list_packages_no_installer(client):
    routes_module.set_hub_installer(None)
    resp = client.get("/api/v1/hub/packages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["packages"] == []


def test_list_packages_empty(client):
    routes_module.set_hub_installer(mock_installer([]))
    resp = client.get("/api/v1/hub/packages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["packages"] == []


def test_list_packages_returns_all(client):
    pkgs = [make_pkg("a"), make_pkg("b")]
    inst = mock_installer(pkgs)
    routes_module.set_hub_installer(inst)
    resp = client.get("/api/v1/hub/packages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert len(data["packages"]) == 2


# ---------------------------------------------------------------------------
# POST /api/v1/hub/packages
# ---------------------------------------------------------------------------


def test_install_no_installer_503(client):
    routes_module.set_hub_installer(None)
    resp = client.post("/api/v1/hub/packages", json={"source_url": "data:text/plain,x=1"})
    assert resp.status_code == 503


def test_install_missing_source_url_422(client):
    routes_module.set_hub_installer(mock_installer())
    resp = client.post("/api/v1/hub/packages", json={})
    assert resp.status_code == 422


def test_install_success_returns_201(client):
    pkg = make_pkg("new-skill")
    inst = mock_installer()
    inst.install = AsyncMock(return_value=pkg)
    routes_module.set_hub_installer(inst)
    resp = client.post("/api/v1/hub/packages", json={"source_url": "data:text/plain,x=1"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "new-skill"


def test_install_scan_blocked_422(client):
    inst = mock_installer()
    inst.install = AsyncMock(side_effect=ScanBlockedError("blocked by scanner"))
    routes_module.set_hub_installer(inst)
    resp = client.post("/api/v1/hub/packages", json={"source_url": "data:text/plain,x=1"})
    assert resp.status_code == 422
    assert "blocked" in resp.json()["detail"].lower()


def test_install_install_error_400(client):
    inst = mock_installer()
    inst.install = AsyncMock(side_effect=InstallError("already installed"))
    routes_module.set_hub_installer(inst)
    resp = client.post("/api/v1/hub/packages", json={"source_url": "data:text/plain,x=1"})
    assert resp.status_code == 400


def test_install_passes_all_fields(client):
    pkg = make_pkg("full-skill")
    inst = mock_installer()
    inst.install = AsyncMock(return_value=pkg)
    routes_module.set_hub_installer(inst)
    body = {
        "source_url": "data:text/plain,x=1",
        "name": "full-skill",
        "version": "2.0.0",
        "description": "desc",
        "author": "Eve",
        "tags": ["t1"],
        "force": True,
    }
    client.post("/api/v1/hub/packages", json=body)
    inst.install.assert_awaited_once_with(
        "data:text/plain,x=1",
        name="full-skill",
        version="2.0.0",
        description="desc",
        author="Eve",
        tags=["t1"],
        force=True,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/hub/packages/{name}
# ---------------------------------------------------------------------------


def test_get_package_no_installer_503(client):
    routes_module.set_hub_installer(None)
    resp = client.get("/api/v1/hub/packages/any")
    assert resp.status_code == 503


def test_get_package_not_found_404(client):
    inst = mock_installer()
    inst._registry.get.return_value = None
    routes_module.set_hub_installer(inst)
    resp = client.get("/api/v1/hub/packages/ghost")
    assert resp.status_code == 404


def test_get_package_success(client):
    pkg = make_pkg("found-skill")
    inst = mock_installer([pkg])
    routes_module.set_hub_installer(inst)
    resp = client.get("/api/v1/hub/packages/found-skill")
    assert resp.status_code == 200
    assert resp.json()["name"] == "found-skill"


# ---------------------------------------------------------------------------
# DELETE /api/v1/hub/packages/{name}
# ---------------------------------------------------------------------------


def test_uninstall_no_installer_503(client):
    routes_module.set_hub_installer(None)
    resp = client.delete("/api/v1/hub/packages/any")
    assert resp.status_code == 503


def test_uninstall_not_found_404(client):
    inst = mock_installer()
    inst.uninstall.side_effect = InstallError("not found")
    routes_module.set_hub_installer(inst)
    resp = client.delete("/api/v1/hub/packages/ghost")
    assert resp.status_code == 404


def test_uninstall_success_204(client):
    inst = mock_installer()
    inst.uninstall.return_value = None
    routes_module.set_hub_installer(inst)
    resp = client.delete("/api/v1/hub/packages/gone")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# PATCH /api/v1/hub/packages/{name}
# ---------------------------------------------------------------------------


def test_patch_no_installer_503(client):
    routes_module.set_hub_installer(None)
    resp = client.patch("/api/v1/hub/packages/any", json={"enabled": True})
    assert resp.status_code == 503


def test_patch_not_found_404(client):
    inst = mock_installer()
    inst._registry.get.return_value = None
    routes_module.set_hub_installer(inst)
    resp = client.patch("/api/v1/hub/packages/ghost", json={"enabled": True})
    assert resp.status_code == 404


def test_patch_enable(client):
    pkg = make_pkg("patchable", enabled=False)
    inst = mock_installer([pkg])
    inst._registry.get.return_value = pkg
    routes_module.set_hub_installer(inst)
    resp = client.patch("/api/v1/hub/packages/patchable", json={"enabled": True})
    assert resp.status_code == 200
    inst._registry.enable.assert_called_once_with("patchable")


def test_patch_disable(client):
    pkg = make_pkg("patchable", enabled=True)
    inst = mock_installer([pkg])
    inst._registry.get.return_value = pkg
    routes_module.set_hub_installer(inst)
    resp = client.patch("/api/v1/hub/packages/patchable", json={"enabled": False})
    assert resp.status_code == 200
    inst._registry.disable.assert_called_once_with("patchable")


def test_patch_no_enabled_field_still_returns_200(client):
    pkg = make_pkg("patchable")
    inst = mock_installer([pkg])
    inst._registry.get.return_value = pkg
    routes_module.set_hub_installer(inst)
    resp = client.patch("/api/v1/hub/packages/patchable", json={"other": "value"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/hub/search
# ---------------------------------------------------------------------------


def test_search_no_installer(client):
    routes_module.set_hub_installer(None)
    resp = client.get("/api/v1/hub/search?q=nlp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["results"] == []


def test_search_returns_results(client):
    pkg = make_pkg("nlp-skill")
    inst = mock_installer([pkg])
    inst._registry.search.return_value = [pkg]
    routes_module.set_hub_installer(inst)
    resp = client.get("/api/v1/hub/search?q=nlp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert data["query"] == "nlp"
    assert len(data["results"]) == 1


def test_search_no_query_returns_all(client):
    pkgs = [make_pkg("a"), make_pkg("b")]
    inst = mock_installer(pkgs)
    inst._registry.search.return_value = pkgs
    routes_module.set_hub_installer(inst)
    resp = client.get("/api/v1/hub/search")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 2


# ---------------------------------------------------------------------------
# POST /api/v1/hub/scan
# ---------------------------------------------------------------------------


def test_scan_no_installer_503(client):
    routes_module.set_hub_installer(None)
    resp = client.post("/api/v1/hub/scan", json={"source_url": "data:text/plain,x=1"})
    assert resp.status_code == 503


def test_scan_missing_source_url_422(client):
    routes_module.set_hub_installer(mock_installer())
    resp = client.post("/api/v1/hub/scan", json={})
    assert resp.status_code == 422


def test_scan_clean_code_returns_safe(client):
    from cortexflow_ai.hub.scanner import ScanResult
    inst = mock_installer()
    inst._fetch_code = AsyncMock(return_value="def hi(): pass")
    inst._scanner = MagicMock()
    inst._scanner.scan_code.return_value = ScanResult(safe=True, scanned_files=1)
    routes_module.set_hub_installer(inst)
    resp = client.post("/api/v1/hub/scan", json={"source_url": "data:text/plain,def+hi():pass"})
    assert resp.status_code == 200
    assert resp.json()["safe"] is True


def test_scan_fetch_error_400(client):
    inst = mock_installer()
    inst._fetch_code = AsyncMock(side_effect=Exception("network error"))
    routes_module.set_hub_installer(inst)
    resp = client.post("/api/v1/hub/scan", json={"source_url": "https://bad.example.com/x.py"})
    assert resp.status_code == 400
