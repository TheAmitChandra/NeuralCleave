"""Cloud deployment utilities for CortexFlow.

Provides configuration validation, manifest generation (Dockerfile,
docker-compose.yml, railway.toml, render.yaml), platform detection,
and Docker pre-flight checks — enabling CortexFlow to be self-hosted
on any Docker-compatible cloud platform.
"""

from cortexflow_ai.cloud.config import CloudDeployConfig
from cortexflow_ai.cloud.health import (
    check_compose,
    check_docker,
    cloud_env_vars,
    detect_platform,
    is_cloud,
)
from cortexflow_ai.cloud.manifests import (
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
