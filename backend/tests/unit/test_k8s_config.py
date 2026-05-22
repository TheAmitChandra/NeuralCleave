"""Tests for K8s deployment configuration dataclasses."""

from __future__ import annotations

import pytest

from app.core.infrastructure.k8s_config import (
    DeploymentConfig,
    ProbeConfig,
    ResourceSpec,
    ServiceKind,
    StorageAccessMode,
    StorageSpec,
)


# ===========================================================================
# TestResourceSpec
# ===========================================================================

class TestResourceSpec:
    def test_default_values(self) -> None:
        spec = ResourceSpec()
        assert spec.cpu_request == "250m"
        assert spec.cpu_limit == "1000m"
        assert spec.memory_request == "512Mi"
        assert spec.memory_limit == "2Gi"

    def test_to_dict_structure(self) -> None:
        spec = ResourceSpec(cpu_request="100m", cpu_limit="500m",
                            memory_request="128Mi", memory_limit="512Mi")
        d = spec.to_dict()
        assert d["requests"]["cpu"] == "100m"
        assert d["requests"]["memory"] == "128Mi"
        assert d["limits"]["cpu"] == "500m"
        assert d["limits"]["memory"] == "512Mi"

    def test_validate_passes_on_valid_spec(self) -> None:
        ResourceSpec().validate()  # should not raise

    def test_validate_raises_on_empty_cpu_request(self) -> None:
        spec = ResourceSpec(cpu_request="")
        with pytest.raises(ValueError, match="cpu_request"):
            spec.validate()

    def test_validate_raises_on_empty_memory_limit(self) -> None:
        spec = ResourceSpec(memory_limit="")
        with pytest.raises(ValueError, match="memory_limit"):
            spec.validate()


# ===========================================================================
# TestStorageSpec
# ===========================================================================

class TestStorageSpec:
    def test_default_values(self) -> None:
        s = StorageSpec()
        assert s.size == "10Gi"
        assert s.access_mode == StorageAccessMode.READ_WRITE_ONCE
        assert s.mount_path == "/data"

    def test_to_dict(self) -> None:
        s = StorageSpec(size="50Gi", mount_path="/storage")
        d = s.to_dict()
        assert d["size"] == "50Gi"
        assert d["mount_path"] == "/storage"
        assert d["access_mode"] == "ReadWriteOnce"


# ===========================================================================
# TestProbeConfig
# ===========================================================================

class TestProbeConfig:
    def test_default_values(self) -> None:
        p = ProbeConfig()
        assert p.path == "/health"
        assert p.port == 8000
        assert p.initial_delay_seconds == 30

    def test_to_dict_structure(self) -> None:
        p = ProbeConfig(path="/ready", port=9090, initial_delay_seconds=10, period_seconds=5)
        d = p.to_dict()
        assert d["httpGet"]["path"] == "/ready"
        assert d["httpGet"]["port"] == 9090
        assert d["initialDelaySeconds"] == 10
        assert d["periodSeconds"] == 5


# ===========================================================================
# TestDeploymentConfig
# ===========================================================================

class TestDeploymentConfig:
    def test_basic_creation(self) -> None:
        cfg = DeploymentConfig(service_name="myapp", image="myapp:1.0", port=8080)
        assert cfg.service_name == "myapp"
        assert cfg.port == 8080
        assert cfg.replicas == 1

    def test_invalid_replicas_raises(self) -> None:
        with pytest.raises(ValueError, match="replicas"):
            DeploymentConfig(service_name="x", image="x:1", port=80, replicas=0)

    def test_invalid_port_raises(self) -> None:
        with pytest.raises(ValueError, match="port"):
            DeploymentConfig(service_name="x", image="x:1", port=99999)

    def test_port_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="port"):
            DeploymentConfig(service_name="x", image="x:1", port=0)

    def test_to_dict_includes_service_name(self) -> None:
        cfg = DeploymentConfig(service_name="svc", image="svc:2.0", port=5000)
        d = cfg.to_dict()
        assert d["service_name"] == "svc"
        assert d["port"] == 5000
        assert "resources" in d

    def test_to_dict_includes_storage_when_set(self) -> None:
        cfg = DeploymentConfig(
            service_name="db", image="db:1", port=5432,
            storage_spec=StorageSpec(size="20Gi"),
        )
        d = cfg.to_dict()
        assert "storage" in d
        assert d["storage"]["size"] == "20Gi"

    def test_to_dict_no_storage_when_not_set(self) -> None:
        cfg = DeploymentConfig(service_name="app", image="app:1", port=8000)
        assert "storage" not in cfg.to_dict()

    def test_labels_include_app_key(self) -> None:
        cfg = DeploymentConfig(service_name="web", image="web:1", port=80)
        assert cfg.to_dict()["labels"]["app"] == "web"


# ===========================================================================
# TestDeploymentConfigFactories
# ===========================================================================

class TestDeploymentConfigFactories:
    def test_for_backend(self) -> None:
        cfg = DeploymentConfig.for_backend()
        assert cfg.service_name == "cortexflow-backend"
        assert cfg.port == 8000
        assert cfg.replicas == 2
        assert cfg.kind == ServiceKind.DEPLOYMENT
        assert cfg.liveness_probe is not None
        assert cfg.readiness_probe is not None

    def test_for_frontend(self) -> None:
        cfg = DeploymentConfig.for_frontend()
        assert cfg.service_name == "cortexflow-frontend"
        assert cfg.port == 3000
        assert cfg.replicas == 2

    def test_for_postgres_is_statefulset(self) -> None:
        cfg = DeploymentConfig.for_postgres()
        assert cfg.kind == ServiceKind.STATEFUL_SET
        assert cfg.storage_spec is not None
        assert cfg.storage_spec.size == "20Gi"

    def test_for_qdrant(self) -> None:
        cfg = DeploymentConfig.for_qdrant()
        assert cfg.service_name == "qdrant"
        assert cfg.port == 6333
        assert cfg.storage_spec.size == "50Gi"

    def test_for_neo4j(self) -> None:
        cfg = DeploymentConfig.for_neo4j()
        assert cfg.kind == ServiceKind.STATEFUL_SET
        assert cfg.port == 7474

    def test_for_redis(self) -> None:
        cfg = DeploymentConfig.for_redis()
        assert cfg.service_name == "redis"
        assert cfg.port == 6379
        assert cfg.storage_spec is not None

    def test_for_service_backend(self) -> None:
        cfg = DeploymentConfig.for_service("backend")
        assert cfg.service_name == "cortexflow-backend"

    def test_for_service_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown-service"):
            DeploymentConfig.for_service("unknown-service")

    def test_all_service_names_complete(self) -> None:
        names = DeploymentConfig.all_service_names()
        assert "backend" in names
        assert "postgres" in names
        assert "qdrant" in names
        assert "neo4j" in names
        assert "redis" in names
        assert "frontend" in names

    def test_all_factories_produce_valid_configs(self) -> None:
        for name in DeploymentConfig.all_service_names():
            cfg = DeploymentConfig.for_service(name)
            assert cfg.replicas >= 1
            assert 1 <= cfg.port <= 65535
            cfg.resource_spec.validate()
