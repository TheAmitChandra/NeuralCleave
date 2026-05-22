"""Kubernetes Deployment Configuration — CortexFlow infrastructure layer.

Provides typed dataclasses that mirror the K8s manifest settings for the
CortexFlow platform.  These objects can be used:
    - to generate manifests programmatically
    - as the source-of-truth for Helm value overrides
    - as structured configuration for CI/CD pipelines

Usage::

    config = DeploymentConfig.for_service("backend")
    print(config.replicas)      # 2
    print(config.resource_spec.cpu_request)  # "250m"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ServiceKind(str, Enum):
    DEPLOYMENT = "Deployment"
    STATEFUL_SET = "StatefulSet"


class StorageAccessMode(str, Enum):
    READ_WRITE_ONCE = "ReadWriteOnce"
    READ_ONLY_MANY = "ReadOnlyMany"
    READ_WRITE_MANY = "ReadWriteMany"


# ---------------------------------------------------------------------------
# Resource specifications
# ---------------------------------------------------------------------------

@dataclass
class ResourceSpec:
    """CPU and memory requests/limits for a K8s container."""

    cpu_request: str = "250m"
    cpu_limit: str = "1000m"
    memory_request: str = "512Mi"
    memory_limit: str = "2Gi"

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests": {
                "cpu": self.cpu_request,
                "memory": self.memory_request,
            },
            "limits": {
                "cpu": self.cpu_limit,
                "memory": self.memory_limit,
            },
        }

    def validate(self) -> None:
        """Raise ValueError if any resource value is empty."""
        for attr in ("cpu_request", "cpu_limit", "memory_request", "memory_limit"):
            if not getattr(self, attr):
                raise ValueError(f"ResourceSpec.{attr} must not be empty")


@dataclass
class StorageSpec:
    """Persistent volume claim specification."""

    size: str = "10Gi"
    access_mode: StorageAccessMode = StorageAccessMode.READ_WRITE_ONCE
    mount_path: str = "/data"

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "access_mode": self.access_mode.value,
            "mount_path": self.mount_path,
        }


# ---------------------------------------------------------------------------
# Probe configuration
# ---------------------------------------------------------------------------

@dataclass
class ProbeConfig:
    """Liveness / readiness probe settings."""

    path: str = "/health"
    port: int = 8000
    initial_delay_seconds: int = 30
    period_seconds: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "httpGet": {"path": self.path, "port": self.port},
            "initialDelaySeconds": self.initial_delay_seconds,
            "periodSeconds": self.period_seconds,
        }


# ---------------------------------------------------------------------------
# Main deployment config
# ---------------------------------------------------------------------------

@dataclass
class DeploymentConfig:
    """Top-level deployment configuration for a CortexFlow service.

    Attributes:
        service_name:    Unique identifier (e.g. "backend", "qdrant").
        image:           Full image reference.
        port:            Primary container port.
        replicas:        Desired replica count.
        kind:            Deployment or StatefulSet.
        resource_spec:   CPU/memory requests & limits.
        storage_spec:    PVC config (only for StatefulSets).
        liveness_probe:  Liveness probe configuration.
        readiness_probe: Readiness probe configuration.
        namespace:       Target K8s namespace.
        labels:          Extra labels to apply to pods.
    """

    service_name: str
    image: str
    port: int
    replicas: int = 1
    kind: ServiceKind = ServiceKind.DEPLOYMENT
    resource_spec: ResourceSpec = field(default_factory=ResourceSpec)
    storage_spec: StorageSpec | None = None
    liveness_probe: ProbeConfig | None = None
    readiness_probe: ProbeConfig | None = None
    namespace: str = "cortexflow"
    labels: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.replicas < 1:
            raise ValueError("replicas must be >= 1")
        if self.port < 1 or self.port > 65535:
            raise ValueError("port must be between 1 and 65535")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "service_name": self.service_name,
            "image": self.image,
            "port": self.port,
            "replicas": self.replicas,
            "kind": self.kind.value,
            "namespace": self.namespace,
            "resources": self.resource_spec.to_dict(),
            "labels": {**self.labels, "app": self.service_name},
        }
        if self.storage_spec:
            d["storage"] = self.storage_spec.to_dict()
        if self.liveness_probe:
            d["liveness_probe"] = self.liveness_probe.to_dict()
        if self.readiness_probe:
            d["readiness_probe"] = self.readiness_probe.to_dict()
        return d

    # ------------------------------------------------------------------
    # Factory helpers — pre-configured for each CortexFlow service
    # ------------------------------------------------------------------

    @classmethod
    def for_backend(cls) -> "DeploymentConfig":
        return cls(
            service_name="cortexflow-backend",
            image="cortexflow/backend:latest",
            port=8000,
            replicas=2,
            kind=ServiceKind.DEPLOYMENT,
            resource_spec=ResourceSpec(
                cpu_request="250m", cpu_limit="1000m",
                memory_request="512Mi", memory_limit="2Gi",
            ),
            liveness_probe=ProbeConfig(path="/health", port=8000, initial_delay_seconds=30),
            readiness_probe=ProbeConfig(path="/health", port=8000, initial_delay_seconds=10, period_seconds=5),
        )

    @classmethod
    def for_frontend(cls) -> "DeploymentConfig":
        return cls(
            service_name="cortexflow-frontend",
            image="cortexflow/frontend:latest",
            port=3000,
            replicas=2,
            kind=ServiceKind.DEPLOYMENT,
            resource_spec=ResourceSpec(
                cpu_request="100m", cpu_limit="500m",
                memory_request="256Mi", memory_limit="1Gi",
            ),
            liveness_probe=ProbeConfig(path="/", port=3000, initial_delay_seconds=15),
            readiness_probe=ProbeConfig(path="/", port=3000, initial_delay_seconds=5, period_seconds=5),
        )

    @classmethod
    def for_postgres(cls) -> "DeploymentConfig":
        return cls(
            service_name="postgres",
            image="postgres:16-alpine",
            port=5432,
            replicas=1,
            kind=ServiceKind.STATEFUL_SET,
            resource_spec=ResourceSpec(
                cpu_request="250m", cpu_limit="1000m",
                memory_request="512Mi", memory_limit="2Gi",
            ),
            storage_spec=StorageSpec(size="20Gi", mount_path="/var/lib/postgresql/data"),
        )

    @classmethod
    def for_qdrant(cls) -> "DeploymentConfig":
        return cls(
            service_name="qdrant",
            image="qdrant/qdrant:v1.9.0",
            port=6333,
            replicas=1,
            kind=ServiceKind.STATEFUL_SET,
            resource_spec=ResourceSpec(
                cpu_request="500m", cpu_limit="2000m",
                memory_request="1Gi", memory_limit="4Gi",
            ),
            storage_spec=StorageSpec(size="50Gi", mount_path="/qdrant/storage"),
        )

    @classmethod
    def for_neo4j(cls) -> "DeploymentConfig":
        return cls(
            service_name="neo4j",
            image="neo4j:5.18-community",
            port=7474,
            replicas=1,
            kind=ServiceKind.STATEFUL_SET,
            resource_spec=ResourceSpec(
                cpu_request="500m", cpu_limit="2000m",
                memory_request="1Gi", memory_limit="4Gi",
            ),
            storage_spec=StorageSpec(size="20Gi", mount_path="/data"),
        )

    @classmethod
    def for_redis(cls) -> "DeploymentConfig":
        return cls(
            service_name="redis",
            image="redis:7-alpine",
            port=6379,
            replicas=1,
            kind=ServiceKind.STATEFUL_SET,
            resource_spec=ResourceSpec(
                cpu_request="100m", cpu_limit="500m",
                memory_request="256Mi", memory_limit="1Gi",
            ),
            storage_spec=StorageSpec(size="10Gi", mount_path="/data"),
        )

    @classmethod
    def for_service(cls, name: str) -> "DeploymentConfig":
        """Return a pre-configured ``DeploymentConfig`` by service name."""
        factories = {
            "backend": cls.for_backend,
            "frontend": cls.for_frontend,
            "postgres": cls.for_postgres,
            "qdrant": cls.for_qdrant,
            "neo4j": cls.for_neo4j,
            "redis": cls.for_redis,
        }
        factory = factories.get(name)
        if factory is None:
            raise KeyError(
                f"No pre-configured DeploymentConfig for service {name!r}. "
                f"Known services: {sorted(factories)}"
            )
        return factory()

    @staticmethod
    def all_service_names() -> list[str]:
        """Return the list of known CortexFlow service names."""
        return ["backend", "frontend", "postgres", "qdrant", "neo4j", "redis"]
