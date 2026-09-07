"""Deployment configuration works both on first boot and with saved TOML."""

import pytest

from neuralcleave.config import load_config


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
