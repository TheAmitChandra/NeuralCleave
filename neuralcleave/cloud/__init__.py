"""Cloud deployment utilities for NeuralCleave.

Provides configuration validation, manifest generation (Dockerfile,
docker-compose.yml, railway.toml, render.yaml), platform detection,
and Docker pre-flight checks — enabling NeuralCleave to be self-hosted
on any Docker-compatible cloud platform.
"""

from neuralcleave.cloud.config import CloudDeployConfig
from neuralcleave.cloud.health import (
    check_compose,
    check_docker,
    cloud_env_vars,
    detect_platform,
    is_cloud,
)
from neuralcleave.cloud.manifests import (
    generate_compose,
    generate_dockerfile,
    generate_railway,
    generate_render,
)

__all__ = [
    "CloudDeployConfig",
    "check_compose",
    "check_docker",
    "cloud_env_vars",
    "detect_platform",
    "is_cloud",
    "generate_compose",
    "generate_dockerfile",
    "generate_railway",
    "generate_render",
]
