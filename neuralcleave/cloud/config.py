"""Cloud deployment configuration with validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_VALID_PYTHON_VERSIONS = ("3.11", "3.12", "3.13")
_VALID_RESTART_POLICIES = ("unless-stopped", "always", "on-failure", "no")


@dataclass
class CloudDeployConfig:
    """Configuration for a NeuralCleave cloud deployment.

    All fields map to knobs in the generated Dockerfile, docker-compose.yml,
    railway.toml and render.yaml.  Call :meth:`validate` to surface errors
    before writing manifests.
    """

    port: int = 7432
    bind: str = "0.0.0.0"
    service_name: str = "NeuralCleave"
    python_version: str = "3.12"
    memory_mb: int = 512
    cpu_count: float = 1.0
    health_path: str = "/health"
    env_vars: dict[str, str] = field(default_factory=dict)
    redis_enabled: bool = True
    qdrant_enabled: bool = True
    restart_policy: str = "unless-stopped"

    def validate(self) -> list[str]:
        """Return a list of validation error strings; empty list means valid."""
        errors: list[str] = []

        if not (1 <= self.port <= 65535):
            errors.append(f"port must be 1–65535, got {self.port}")

        if not self.bind:
            errors.append("bind must not be empty")

        if not self.service_name:
            errors.append("service_name must not be empty")
        elif not _SERVICE_NAME_RE.match(self.service_name):
            errors.append(
                f"service_name must start with alphanumeric and contain only "
                f"letters, digits, hyphens, or underscores; got {self.service_name!r}"
            )

        if self.python_version not in _VALID_PYTHON_VERSIONS:
            errors.append(
                f"python_version must be one of "
                f"{', '.join(_VALID_PYTHON_VERSIONS)}; got {self.python_version!r}"
            )

        if self.memory_mb < 128:
            errors.append(f"memory_mb must be >= 128, got {self.memory_mb}")

        if self.cpu_count <= 0:
            errors.append(f"cpu_count must be > 0, got {self.cpu_count}")

        if not self.health_path.startswith("/"):
            errors.append(
                f"health_path must start with '/'; got {self.health_path!r}"
            )

        if self.restart_policy not in _VALID_RESTART_POLICIES:
            errors.append(
                f"restart_policy must be one of "
                f"{', '.join(_VALID_RESTART_POLICIES)}; got {self.restart_policy!r}"
            )

        return errors

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CloudDeployConfig:
        """Construct from a plain dictionary, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)  # type: ignore[arg-type]
