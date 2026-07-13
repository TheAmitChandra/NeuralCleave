"""Generate cloud deployment manifests from a CloudDeployConfig."""

from __future__ import annotations

from cortexflow_ai.cloud.config import CloudDeployConfig


def generate_dockerfile(config: CloudDeployConfig) -> str:
    """Return Dockerfile content for the given *config*."""
    health_url = f"http://localhost:{config.port}{config.health_path}"
    return (
        f"# syntax=docker/dockerfile:1\n"
        f"FROM python:{config.python_version}-slim AS base\n"
        f"WORKDIR /app\n"
        f"ENV PYTHONUNBUFFERED=1 \\\n"
        f"    PYTHONDONTWRITEBYTECODE=1 \\\n"
        f"    PIP_NO_CACHE_DIR=1\n"
        f"\n"
        f"FROM base AS deps\n"
        f"COPY pyproject.toml ./\n"
        f"RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir .\n"
        f"\n"
        f"FROM deps AS runtime\n"
        f"COPY cortexflow_ai/ ./cortexflow_ai/\n"
        f"\n"
        f"ENV CORTEXFLOW_PORT={config.port} \\\n"
        f"    CORTEXFLOW_BIND={config.bind}\n"
        f"\n"
        f"EXPOSE {config.port}\n"
        f"\n"
        f"HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \\\n"
        f"  CMD python -c \"import urllib.request; urllib.request.urlopen('{health_url}')\"\n"
        f"\n"
        f'CMD ["python", "-m", "uvicorn", "cortexflow_ai.gateway.main:app", '
        f'"--host", "{config.bind}", "--port", "{config.port}"]\n'
    )


def generate_compose(config: CloudDeployConfig) -> str:
    """Return docker-compose.yml content for the given *config*."""
    lines: list[str] = [
        'version: "3.9"',
        "",
        "services:",
        f"  {config.service_name}:",
        "    build: .",
        "    ports:",
        f'      - "{config.port}:{config.port}"',
        "    environment:",
        "      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}",
        "      - GEMINI_API_KEY=${GEMINI_API_KEY:-}",
        "      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}",
    ]

    if config.redis_enabled:
        lines.append("      - REDIS_URL=redis://redis:6379")
    if config.qdrant_enabled:
        lines.append("      - QDRANT_URL=http://qdrant:6333")

    lines += [
        "    volumes:",
        "      - cortexflow_data:/root/.cortexflow",
    ]

    deps: list[str] = []
    if config.redis_enabled:
        deps.append("redis")
    if config.qdrant_enabled:
        deps.append("qdrant")

    if deps:
        lines.append("    depends_on:")
        for dep in deps:
            lines.append(f"      - {dep}")

    lines += [
        f"    restart: {config.restart_policy}",
        "    healthcheck:",
        '      test: ["CMD", "python", "-c", '
        f'"import urllib.request; '
        f"urllib.request.urlopen('http://localhost:{config.port}{config.health_path}')\"]",
        "      interval: 30s",
        "      timeout: 10s",
        "      retries: 3",
    ]

    if config.redis_enabled:
        lines += [
            "",
            "  redis:",
            "    image: redis:7-alpine",
            "    volumes:",
            "      - redis_data:/data",
            "    restart: unless-stopped",
        ]

    if config.qdrant_enabled:
        lines += [
            "",
            "  qdrant:",
            "    image: qdrant/qdrant:latest",
            "    volumes:",
            "      - qdrant_data:/qdrant/storage",
            "    restart: unless-stopped",
        ]

    lines += [
        "",
        "volumes:",
        "  cortexflow_data:",
    ]
    if config.redis_enabled:
        lines.append("  redis_data:")
    if config.qdrant_enabled:
        lines.append("  qdrant_data:")

    return "\n".join(lines) + "\n"


def generate_railway(config: CloudDeployConfig) -> str:
    """Return railway.toml content for the given *config*."""
    return (
        "[build]\n"
        'builder = "DOCKERFILE"\n'
        'dockerfilePath = "Dockerfile"\n'
        "\n"
        "[deploy]\n"
        f'startCommand = "python -m uvicorn cortexflow_ai.gateway.main:app '
        f'--host 0.0.0.0 --port {config.port}"\n'
        f'healthcheckPath = "{config.health_path}"\n'
        "healthcheckTimeout = 30\n"
        'restartPolicyType = "ON_FAILURE"\n'
        "restartPolicyMaxRetries = 3\n"
    )


def generate_render(config: CloudDeployConfig) -> str:
    """Return render.yaml content for the given *config*."""
    return (
        "services:\n"
        "  - type: web\n"
        f"    name: {config.service_name}\n"
        "    env: docker\n"
        "    dockerfilePath: Dockerfile\n"
        "    plan: starter\n"
        f"    port: {config.port}\n"
        f"    healthCheckPath: {config.health_path}\n"
        "    autoDeploy: true\n"
        "    envVars:\n"
        "      - key: ANTHROPIC_API_KEY\n"
        "        sync: false\n"
        "      - key: GEMINI_API_KEY\n"
        "        sync: false\n"
        "      - key: DEEPSEEK_API_KEY\n"
        "        sync: false\n"
        "      - key: CORTEXFLOW_BIND\n"
        '        value: "0.0.0.0"\n'
        "      - key: CORTEXFLOW_PORT\n"
        f'        value: "{config.port}"\n'
    )
