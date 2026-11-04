"""Deployment configuration works both on first boot and with saved TOML."""

from pathlib import Path

import pytest

from neuralcleave.config import load_config

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("existing", [False, True])
def test_service_environment_applied_with_or_without_config(tmp_path, monkeypatch, existing):
    path = tmp_path / "config.toml"
    if existing:
        path.write_text('[memory]\nredis_url="redis://old:6379"\n[gateway]\napi_key="old"\n')
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("NEURALCLEAVE_API_KEY", "deployment-secret")
    config = load_config(path)
    assert config.memory.redis_url == "redis://redis:6379"
    assert config.memory.qdrant_url == "http://qdrant:6333"
    assert config.gateway.api_key == "deployment-secret"


def test_empty_environment_preserves_saved_config(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('[memory]\nredis_url="redis://saved:6379"\n[gateway]\napi_key="saved"\n')
    for name in ("REDIS_URL", "QDRANT_URL", "NEURALCLEAVE_API_KEY"):
        monkeypatch.setenv(name, "")
    config = load_config(path)
    assert config.memory.redis_url == "redis://saved:6379"
    assert config.gateway.api_key == "saved"


_LISTEN_VARS = ("NEURALCLEAVE_BIND", "NEURALCLEAVE_PORT", "NeuralCleave_BIND", "NeuralCleave_PORT")


@pytest.fixture
def clean_listen_env(monkeypatch):
    for name in _LISTEN_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("existing", [False, True])
def test_listen_address_environment_overrides_config(tmp_path, clean_listen_env, existing):
    path = tmp_path / "config.toml"
    if existing:
        path.write_text('[gateway]\nbind="127.0.0.1"\nport=7000\n')
    clean_listen_env.setenv("NEURALCLEAVE_BIND", "0.0.0.0")
    clean_listen_env.setenv("NEURALCLEAVE_PORT", "9123")
    config = load_config(path)
    assert config.gateway.bind == "0.0.0.0"
    assert config.gateway.port == 9123


def test_legacy_listen_variable_names_still_apply(tmp_path, clean_listen_env):
    clean_listen_env.setenv("NeuralCleave_BIND", "0.0.0.0")
    clean_listen_env.setenv("NeuralCleave_PORT", "9124")
    config = load_config(tmp_path / "missing.toml")
    assert config.gateway.bind == "0.0.0.0"
    assert config.gateway.port == 9124


def test_canonical_listen_variables_win_over_legacy(tmp_path, clean_listen_env):
    clean_listen_env.setenv("NEURALCLEAVE_PORT", "9125")
    clean_listen_env.setenv("NeuralCleave_PORT", "9126")
    assert load_config(tmp_path / "missing.toml").gateway.port == 9125


@pytest.mark.parametrize("bad", ["not-a-port", "0", "70000", "-5"])
def test_invalid_port_environment_keeps_saved_port(tmp_path, clean_listen_env, bad):
    path = tmp_path / "config.toml"
    path.write_text("[gateway]\nport=7001\n")
    clean_listen_env.setenv("NEURALCLEAVE_PORT", bad)
    assert load_config(path).gateway.port == 7001


def test_empty_listen_environment_preserves_saved_config(tmp_path, clean_listen_env):
    path = tmp_path / "config.toml"
    path.write_text('[gateway]\nbind="127.0.0.1"\nport=7002\n')
    clean_listen_env.setenv("NEURALCLEAVE_BIND", "")
    clean_listen_env.setenv("NEURALCLEAVE_PORT", "")
    config = load_config(path)
    assert config.gateway.bind == "127.0.0.1"
    assert config.gateway.port == 7002


def test_root_container_uses_installed_cli_and_canonical_state_directory():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["neuralcleave"]' in dockerfile
    assert 'CMD ["start", "--bind", "0.0.0.0"]' in dockerfile
    assert "/root/.neuralcleave/workspace" in dockerfile
    assert "neuralcleave-gateway:latest" in compose
    assert "NeuralCleave_data:/root/.neuralcleave" in compose
    assert "REDIS_URL=redis://redis:6379" in compose
    assert "QDRANT_URL=http://qdrant:6333" in compose


def test_docker_pull_requests_boot_the_image_and_probe_readiness():
    workflow = (ROOT / ".github/workflows/ci-docker.yml").read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "docker run --detach" in workflow
    assert "http://127.0.0.1:7432/health" in workflow
    assert "http://127.0.0.1:7432/ready" in workflow


def test_root_manifests_use_canonical_listen_variable_names():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for content in (dockerfile, render):
        assert "NEURALCLEAVE_PORT" in content
        assert "NEURALCLEAVE_BIND" in content
        assert "NeuralCleave_PORT" not in content
        assert "NeuralCleave_BIND" not in content
    # Host-side port mapping prefers the canonical name, legacy name as fallback.
    assert "${NEURALCLEAVE_PORT:-${NeuralCleave_PORT:-7432}}:7432" in compose
