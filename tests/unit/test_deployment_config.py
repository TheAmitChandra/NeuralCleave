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
