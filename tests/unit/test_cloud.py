"""Tests for neuralcleave.cloud — config, manifests, health, and CLI."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

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

# ═══════════════════════════════════════════════════════════════════════════════
# CloudDeployConfig — defaults and field assignment
# ═══════════════════════════════════════════════════════════════════════════════


def test_default_port():
    assert CloudDeployConfig().port == 7432


def test_default_bind():
    assert CloudDeployConfig().bind == "0.0.0.0"


def test_default_service_name():
    assert CloudDeployConfig().service_name == "NeuralCleave"


def test_default_python_version():
    assert CloudDeployConfig().python_version == "3.12"


def test_default_memory_mb():
    assert CloudDeployConfig().memory_mb == 512


def test_default_cpu_count():
    assert CloudDeployConfig().cpu_count == 1.0


def test_default_health_path():
    assert CloudDeployConfig().health_path == "/health"


def test_default_redis_enabled():
    assert CloudDeployConfig().redis_enabled is True


def test_default_qdrant_enabled():
    assert CloudDeployConfig().qdrant_enabled is True


def test_default_restart_policy():
    assert CloudDeployConfig().restart_policy == "unless-stopped"


def test_default_env_vars_empty():
    assert CloudDeployConfig().env_vars == {}


def test_custom_port():
    cfg = CloudDeployConfig(port=8080)
    assert cfg.port == 8080


def test_custom_service_name():
    cfg = CloudDeployConfig(service_name="my-bot")
    assert cfg.service_name == "my-bot"


def test_custom_python_version():
    cfg = CloudDeployConfig(python_version="3.11")
    assert cfg.python_version == "3.11"


def test_custom_memory_mb():
    cfg = CloudDeployConfig(memory_mb=1024)
    assert cfg.memory_mb == 1024


def test_redis_disabled():
    cfg = CloudDeployConfig(redis_enabled=False)
    assert cfg.redis_enabled is False


def test_qdrant_disabled():
    cfg = CloudDeployConfig(qdrant_enabled=False)
    assert cfg.qdrant_enabled is False


def test_env_vars_stored():
    cfg = CloudDeployConfig(env_vars={"FOO": "bar"})
    assert cfg.env_vars == {"FOO": "bar"}


# ═══════════════════════════════════════════════════════════════════════════════
# CloudDeployConfig — validate()
# ═══════════════════════════════════════════════════════════════════════════════


def test_validate_defaults_ok():
    assert CloudDeployConfig().validate() == []


def test_validate_port_zero():
    errors = CloudDeployConfig(port=0).validate()
    assert any("port" in e for e in errors)


def test_validate_port_negative():
    errors = CloudDeployConfig(port=-1).validate()
    assert any("port" in e for e in errors)


def test_validate_port_too_high():
    errors = CloudDeployConfig(port=65536).validate()
    assert any("port" in e for e in errors)


def test_validate_port_65535_ok():
    assert CloudDeployConfig(port=65535).validate() == []


def test_validate_port_1_ok():
    assert CloudDeployConfig(port=1).validate() == []


def test_validate_memory_too_low():
    errors = CloudDeployConfig(memory_mb=64).validate()
    assert any("memory" in e for e in errors)


def test_validate_memory_exactly_128_ok():
    assert CloudDeployConfig(memory_mb=128).validate() == []


def test_validate_cpu_zero():
    errors = CloudDeployConfig(cpu_count=0.0).validate()
    assert any("cpu" in e for e in errors)


def test_validate_cpu_negative():
    errors = CloudDeployConfig(cpu_count=-0.5).validate()
    assert any("cpu" in e for e in errors)


def test_validate_cpu_positive_ok():
    assert CloudDeployConfig(cpu_count=0.1).validate() == []


def test_validate_empty_service_name():
    errors = CloudDeployConfig(service_name="").validate()
    assert any("service_name" in e for e in errors)


def test_validate_service_name_with_spaces():
    errors = CloudDeployConfig(service_name="my bot").validate()
    assert any("service_name" in e for e in errors)


def test_validate_service_name_with_hyphens_ok():
    assert CloudDeployConfig(service_name="my-bot-v2").validate() == []


def test_validate_service_name_with_underscores_ok():
    assert CloudDeployConfig(service_name="my_bot").validate() == []


def test_validate_service_name_starts_digit_ok():
    assert CloudDeployConfig(service_name="0bot").validate() == []


def test_validate_health_path_no_slash():
    errors = CloudDeployConfig(health_path="health").validate()
    assert any("health_path" in e for e in errors)


def test_validate_health_path_with_slash_ok():
    assert CloudDeployConfig(health_path="/api/health").validate() == []


def test_validate_invalid_python_version():
    errors = CloudDeployConfig(python_version="3.10").validate()
    assert any("python_version" in e for e in errors)


def test_validate_python_311_ok():
    assert CloudDeployConfig(python_version="3.11").validate() == []


def test_validate_python_312_ok():
    assert CloudDeployConfig(python_version="3.12").validate() == []


def test_validate_python_313_ok():
    assert CloudDeployConfig(python_version="3.13").validate() == []


def test_validate_invalid_restart_policy():
    errors = CloudDeployConfig(restart_policy="never").validate()
    assert any("restart_policy" in e for e in errors)


def test_validate_restart_policy_always_ok():
    assert CloudDeployConfig(restart_policy="always").validate() == []


def test_validate_restart_policy_on_failure_ok():
    assert CloudDeployConfig(restart_policy="on-failure").validate() == []


def test_validate_restart_policy_no_ok():
    assert CloudDeployConfig(restart_policy="no").validate() == []


def test_validate_multiple_errors():
    cfg = CloudDeployConfig(port=0, memory_mb=64, service_name="")
    errors = cfg.validate()
    assert len(errors) >= 3


# ═══════════════════════════════════════════════════════════════════════════════
# CloudDeployConfig — from_dict()
# ═══════════════════════════════════════════════════════════════════════════════


def test_from_dict_basic():
    cfg = CloudDeployConfig.from_dict({"port": 9000, "service_name": "prod"})
    assert cfg.port == 9000
    assert cfg.service_name == "prod"


def test_from_dict_ignores_unknown_keys():
    cfg = CloudDeployConfig.from_dict({"port": 8000, "unknown_key": "ignored"})
    assert cfg.port == 8000


def test_from_dict_empty_uses_defaults():
    cfg = CloudDeployConfig.from_dict({})
    assert cfg == CloudDeployConfig()


def test_from_dict_redis_disabled():
    cfg = CloudDeployConfig.from_dict({"redis_enabled": False})
    assert cfg.redis_enabled is False


# ═══════════════════════════════════════════════════════════════════════════════
# generate_dockerfile
# ═══════════════════════════════════════════════════════════════════════════════


def test_dockerfile_contains_from_python():
    content = generate_dockerfile(CloudDeployConfig())
    assert "FROM python:3.12-slim" in content


def test_dockerfile_exposes_port():
    content = generate_dockerfile(CloudDeployConfig(port=9000))
    assert "EXPOSE 9000" in content


def test_dockerfile_env_port():
    content = generate_dockerfile(CloudDeployConfig(port=9000))
    assert "NeuralCleave_PORT=9000" in content


def test_dockerfile_custom_python_version():
    content = generate_dockerfile(CloudDeployConfig(python_version="3.11"))
    assert "FROM python:3.11-slim" in content


def test_dockerfile_healthcheck_present():
    content = generate_dockerfile(CloudDeployConfig())
    assert "HEALTHCHECK" in content


def test_dockerfile_healthcheck_uses_health_path():
    content = generate_dockerfile(CloudDeployConfig(health_path="/ping"))
    assert "/ping" in content


def test_dockerfile_cmd_present():
    content = generate_dockerfile(CloudDeployConfig())
    assert "CMD" in content


def test_dockerfile_workdir():
    content = generate_dockerfile(CloudDeployConfig())
    assert "WORKDIR /app" in content


def test_dockerfile_copy_NeuralCleave():
    content = generate_dockerfile(CloudDeployConfig())
    assert "COPY neuralcleave" in content


# ═══════════════════════════════════════════════════════════════════════════════
# generate_compose
# ═══════════════════════════════════════════════════════════════════════════════


def test_compose_contains_version():
    content = generate_compose(CloudDeployConfig())
    assert 'version: "3.9"' in content


def test_compose_contains_service_name():
    content = generate_compose(CloudDeployConfig(service_name="mybot"))
    assert "mybot:" in content


def test_compose_redis_present_by_default():
    content = generate_compose(CloudDeployConfig())
    assert "redis:" in content
    assert "redis_data:" in content


def test_compose_redis_absent_when_disabled():
    content = generate_compose(CloudDeployConfig(redis_enabled=False))
    assert "image: redis" not in content
    assert "redis_data:" not in content


def test_compose_qdrant_present_by_default():
    content = generate_compose(CloudDeployConfig())
    assert "qdrant:" in content
    assert "qdrant_data:" in content


def test_compose_qdrant_absent_when_disabled():
    content = generate_compose(CloudDeployConfig(qdrant_enabled=False))
    assert "qdrant/qdrant" not in content
    assert "qdrant_data:" not in content


def test_compose_port_mapping():
    content = generate_compose(CloudDeployConfig(port=9001))
    assert "9001:9001" in content


def test_compose_restart_policy():
    content = generate_compose(CloudDeployConfig(restart_policy="always"))
    assert "restart: always" in content


def test_compose_anthropic_env_placeholder():
    content = generate_compose(CloudDeployConfig())
    assert "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY" in content


def test_compose_gemini_env_placeholder():
    content = generate_compose(CloudDeployConfig())
    assert "GEMINI_API_KEY=${GEMINI_API_KEY" in content


def test_compose_healthcheck():
    content = generate_compose(CloudDeployConfig())
    assert "healthcheck:" in content


def test_compose_volumes_section():
    content = generate_compose(CloudDeployConfig())
    assert "volumes:" in content
    assert "NeuralCleave_data:" in content


def test_compose_redis_env_absent_when_disabled():
    content = generate_compose(CloudDeployConfig(redis_enabled=False))
    assert "REDIS_URL" not in content


def test_compose_qdrant_env_absent_when_disabled():
    content = generate_compose(CloudDeployConfig(qdrant_enabled=False))
    assert "QDRANT_URL" not in content


def test_compose_depends_on_both():
    content = generate_compose(CloudDeployConfig())
    assert "depends_on:" in content
    assert "- redis" in content
    assert "- qdrant" in content


def test_compose_no_depends_when_no_services():
    content = generate_compose(CloudDeployConfig(redis_enabled=False, qdrant_enabled=False))
    assert "depends_on:" not in content


# ═══════════════════════════════════════════════════════════════════════════════
# generate_railway
# ═══════════════════════════════════════════════════════════════════════════════


def test_railway_builder_dockerfile():
    content = generate_railway(CloudDeployConfig())
    assert 'builder = "DOCKERFILE"' in content


def test_railway_healthcheck_path():
    content = generate_railway(CloudDeployConfig(health_path="/ping"))
    assert 'healthcheckPath = "/ping"' in content


def test_railway_healthcheck_timeout():
    content = generate_railway(CloudDeployConfig())
    assert "healthcheckTimeout = 30" in content


def test_railway_restart_policy():
    content = generate_railway(CloudDeployConfig())
    assert 'restartPolicyType = "ON_FAILURE"' in content


def test_railway_start_command_contains_port():
    content = generate_railway(CloudDeployConfig(port=9090))
    assert "9090" in content


def test_railway_dockerfile_path():
    content = generate_railway(CloudDeployConfig())
    assert 'dockerfilePath = "Dockerfile"' in content


# ═══════════════════════════════════════════════════════════════════════════════
# generate_render
# ═══════════════════════════════════════════════════════════════════════════════


def test_render_service_name():
    content = generate_render(CloudDeployConfig(service_name="cf-prod"))
    assert "name: cf-prod" in content


def test_render_port():
    content = generate_render(CloudDeployConfig(port=8080))
    assert "port: 8080" in content


def test_render_health_check_path():
    content = generate_render(CloudDeployConfig(health_path="/up"))
    assert "healthCheckPath: /up" in content


def test_render_auto_deploy():
    content = generate_render(CloudDeployConfig())
    assert "autoDeploy: true" in content


def test_render_anthropic_key_env():
    content = generate_render(CloudDeployConfig())
    assert "ANTHROPIC_API_KEY" in content


def test_render_gemini_key_env():
    content = generate_render(CloudDeployConfig())
    assert "GEMINI_API_KEY" in content


def test_render_deepseek_key_env():
    content = generate_render(CloudDeployConfig())
    assert "DEEPSEEK_API_KEY" in content


def test_render_env_docker():
    content = generate_render(CloudDeployConfig())
    assert "env: docker" in content


def test_render_dockerfile_path():
    content = generate_render(CloudDeployConfig())
    assert "dockerfilePath: Dockerfile" in content


# ═══════════════════════════════════════════════════════════════════════════════
# detect_platform
# ═══════════════════════════════════════════════════════════════════════════════


def _clean_env(*keys: str):
    """Context manager that removes given env vars, restores on exit."""
    import contextlib

    @contextlib.contextmanager
    def _mgr():
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            yield
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    return _mgr()


def test_detect_platform_none_by_default():
    all_vars = (
        "RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_NAME", "RAILWAY_PROJECT_ID",
        "RENDER", "RENDER_SERVICE_NAME", "RENDER_SERVICE_ID",
        "FLY_APP_NAME", "FLY_REGION", "FLY_ALLOC_ID",
        "DYNO", "HEROKU_APP_NAME",
        "DO_APP_ID", "DO_APP_NAME",
    )
    saved = {k: os.environ.pop(k, None) for k in all_vars}
    try:
        assert detect_platform() is None
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_detect_platform_railway_environment():
    with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
        assert detect_platform() == "railway"


def test_detect_platform_railway_service_name():
    with patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "gateway"}):
        assert detect_platform() == "railway"


def test_detect_platform_railway_project_id():
    with patch.dict(os.environ, {"RAILWAY_PROJECT_ID": "abc123"}):
        assert detect_platform() == "railway"


def test_detect_platform_render():
    with patch.dict(os.environ, {"RENDER": "true"}):
        assert detect_platform() == "render"


def test_detect_platform_render_service_name():
    with patch.dict(os.environ, {"RENDER_SERVICE_NAME": "NeuralCleave"}):
        assert detect_platform() == "render"


def test_detect_platform_render_service_id():
    with patch.dict(os.environ, {"RENDER_SERVICE_ID": "srv-abc"}):
        assert detect_platform() == "render"


def test_detect_platform_fly_app_name():
    with patch.dict(os.environ, {"FLY_APP_NAME": "NeuralCleave"}):
        assert detect_platform() == "fly"


def test_detect_platform_fly_region():
    with patch.dict(os.environ, {"FLY_REGION": "lax"}):
        assert detect_platform() == "fly"


def test_detect_platform_fly_alloc_id():
    with patch.dict(os.environ, {"FLY_ALLOC_ID": "alloc-1"}):
        assert detect_platform() == "fly"


def test_detect_platform_heroku_dyno():
    with patch.dict(os.environ, {"DYNO": "web.1"}):
        assert detect_platform() == "heroku"


def test_detect_platform_heroku_app_name():
    with patch.dict(os.environ, {"HEROKU_APP_NAME": "my-app"}):
        assert detect_platform() == "heroku"


def test_detect_platform_digitalocean_app_id():
    with patch.dict(os.environ, {"DO_APP_ID": "do-app-123"}):
        assert detect_platform() == "digitalocean"


def test_detect_platform_digitalocean_app_name():
    with patch.dict(os.environ, {"DO_APP_NAME": "NeuralCleave"}):
        assert detect_platform() == "digitalocean"


def test_detect_platform_railway_wins_over_render():
    with patch.dict(os.environ, {
        "RAILWAY_ENVIRONMENT": "production",
        "RENDER": "true",
    }):
        assert detect_platform() == "railway"


# ═══════════════════════════════════════════════════════════════════════════════
# is_cloud
# ═══════════════════════════════════════════════════════════════════════════════


def test_is_cloud_false_locally():
    with patch("neuralcleave.cloud.health.detect_platform", return_value=None):
        assert is_cloud() is False


def test_is_cloud_true_on_railway():
    with patch("neuralcleave.cloud.health.detect_platform", return_value="railway"):
        assert is_cloud() is True


def test_is_cloud_true_on_render():
    with patch("neuralcleave.cloud.health.detect_platform", return_value="render"):
        assert is_cloud() is True


# ═══════════════════════════════════════════════════════════════════════════════
# cloud_env_vars
# ═══════════════════════════════════════════════════════════════════════════════


def test_cloud_env_vars_empty_locally():
    all_vars = (
        "RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_NAME", "RAILWAY_PROJECT_ID",
        "RENDER", "RENDER_SERVICE_NAME", "RENDER_SERVICE_ID",
        "FLY_APP_NAME", "FLY_REGION", "FLY_ALLOC_ID",
        "DYNO", "HEROKU_APP_NAME", "DO_APP_ID", "DO_APP_NAME",
    )
    saved = {k: os.environ.pop(k, None) for k in all_vars}
    try:
        assert cloud_env_vars() == {}
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_cloud_env_vars_returns_set_vars():
    with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "prod", "RENDER": "true"}):
        result = cloud_env_vars()
        assert result.get("RAILWAY_ENVIRONMENT") == "prod"
        assert result.get("RENDER") == "true"


def test_cloud_env_vars_ignores_non_cloud_vars():
    with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "prod", "MY_SECRET": "x"}):
        result = cloud_env_vars()
        assert "MY_SECRET" not in result
        assert "RAILWAY_ENVIRONMENT" in result


# ═══════════════════════════════════════════════════════════════════════════════
# check_docker
# ═══════════════════════════════════════════════════════════════════════════════


def test_check_docker_not_found():
    with patch("shutil.which", return_value=None):
        ok, msg = check_docker()
    assert ok is False
    assert "not found" in msg


def test_check_docker_found_returns_version():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Docker version 24.0.5, build ced0996"
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = check_docker()
    assert ok is True
    assert "Docker version" in msg


def test_check_docker_nonzero_returncode():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "cannot connect to daemon"
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = check_docker()
    assert ok is False
    assert "daemon" in msg


def test_check_docker_timeout():
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 5)):
            ok, msg = check_docker()
    assert ok is False
    assert "timed out" in msg


def test_check_docker_oserror():
    with patch("shutil.which", return_value="/usr/bin/docker"):
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            ok, msg = check_docker()
    assert ok is False
    assert "permission denied" in msg


# ═══════════════════════════════════════════════════════════════════════════════
# check_compose
# ═══════════════════════════════════════════════════════════════════════════════


def test_check_compose_v2_plugin_available():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Docker Compose version v2.20.3"
    with patch("subprocess.run", return_value=mock_result):
        ok, msg = check_compose()
    assert ok is True
    assert "Compose" in msg


def test_check_compose_v2_fails_v1_available():
    v2_fail = MagicMock()
    v2_fail.returncode = 1
    v2_fail.stdout = ""
    v2_fail.stderr = ""
    v1_ok = MagicMock()
    v1_ok.returncode = 0
    v1_ok.stdout = "docker-compose version 1.29.2"
    with patch("subprocess.run", side_effect=[v2_fail, v1_ok]):
        with patch("shutil.which", return_value="/usr/local/bin/docker-compose"):
            ok, msg = check_compose()
    assert ok is True
    assert "v1 standalone" in msg


def test_check_compose_neither_found():
    with patch("subprocess.run", side_effect=OSError("not found")):
        with patch("shutil.which", return_value=None):
            ok, msg = check_compose()
    assert ok is False
    assert "not found" in msg.lower() or "neither" in msg.lower()


def test_check_compose_v2_timeout_v1_fallback():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 5)):
        with patch("shutil.which", return_value=None):
            ok, msg = check_compose()
    assert ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — neuralcleave cloud check
# ═══════════════════════════════════════════════════════════════════════════════


def test_cli_cloud_check_docker_available():
    from neuralcleave.cli import cli

    runner = CliRunner()
    with patch("neuralcleave.cloud.health.check_docker", return_value=(True, "Docker 24.0")):
        with patch("neuralcleave.cloud.health.check_compose", return_value=(True, "Compose v2")):
            with patch("neuralcleave.cloud.health.detect_platform", return_value=None):
                result = runner.invoke(cli, ["cloud", "check"])
    assert result.exit_code == 0
    assert "available" in result.output


def test_cli_cloud_check_exits_1_when_docker_missing():
    from neuralcleave.cli import cli

    runner = CliRunner()
    with patch("neuralcleave.cloud.health.check_docker", return_value=(False, "not found")):
        with patch("neuralcleave.cloud.health.check_compose", return_value=(False, "not found")):
            with patch("neuralcleave.cloud.health.detect_platform", return_value=None):
                result = runner.invoke(cli, ["cloud", "check"])
    assert result.exit_code != 0


def test_cli_cloud_check_shows_platform_when_detected():
    from neuralcleave.cli import cli

    runner = CliRunner()
    with patch("neuralcleave.cloud.health.check_docker", return_value=(True, "Docker 24.0")):
        with patch("neuralcleave.cloud.health.check_compose", return_value=(True, "v2")):
            with patch("neuralcleave.cloud.health.detect_platform", return_value="railway"):
                result = runner.invoke(cli, ["cloud", "check"])
    assert "railway" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — neuralcleave cloud generate
# ═══════════════════════════════════════════════════════════════════════════════


def test_cli_cloud_generate_creates_dockerfile(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["cloud", "generate", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "Dockerfile").exists()


def test_cli_cloud_generate_creates_compose(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["cloud", "generate", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "docker-compose.yml").exists()


def test_cli_cloud_generate_creates_railway_toml(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["cloud", "generate", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "railway.toml").exists()


def test_cli_cloud_generate_creates_render_yaml(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["cloud", "generate", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "render.yaml").exists()


def test_cli_cloud_generate_custom_port(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli, ["cloud", "generate", "--output-dir", str(tmp_path), "--port", "9000"]
    )
    assert result.exit_code == 0
    compose = (tmp_path / "docker-compose.yml").read_text()
    assert "9000" in compose


def test_cli_cloud_generate_no_redis(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli, ["cloud", "generate", "--output-dir", str(tmp_path), "--no-redis"]
    )
    assert result.exit_code == 0
    compose = (tmp_path / "docker-compose.yml").read_text()
    assert "image: redis" not in compose


def test_cli_cloud_generate_no_qdrant(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli, ["cloud", "generate", "--output-dir", str(tmp_path), "--no-qdrant"]
    )
    assert result.exit_code == 0
    compose = (tmp_path / "docker-compose.yml").read_text()
    assert "qdrant/qdrant" not in compose


def test_cli_cloud_generate_custom_service_name(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli, ["cloud", "generate", "--output-dir", str(tmp_path), "--service-name", "mybot"]
    )
    assert result.exit_code == 0
    compose = (tmp_path / "docker-compose.yml").read_text()
    assert "mybot:" in compose


def test_cli_cloud_generate_custom_python_version(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["cloud", "generate", "--output-dir", str(tmp_path), "--python-version", "3.11"],
    )
    assert result.exit_code == 0
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "3.11" in dockerfile


def test_cli_cloud_generate_validation_error_exits_1(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli, ["cloud", "generate", "--output-dir", str(tmp_path), "--port", "0"]
    )
    assert result.exit_code != 0


def test_cli_cloud_generate_prints_next_steps(tmp_path):
    from neuralcleave.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["cloud", "generate", "--output-dir", str(tmp_path)])
    assert "docker compose" in result.output or "railway" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — neuralcleave cloud status
# ═══════════════════════════════════════════════════════════════════════════════


def test_cli_cloud_status_shows_local_when_no_platform():
    from neuralcleave.cli import cli

    runner = CliRunner()
    with patch("neuralcleave.cloud.health.detect_platform", return_value=None):
        with patch("neuralcleave.cloud.health.cloud_env_vars", return_value={}):
            result = runner.invoke(cli, ["cloud", "status"])
    assert result.exit_code == 0
    assert "local" in result.output


def test_cli_cloud_status_shows_platform_name():
    from neuralcleave.cli import cli

    runner = CliRunner()
    with patch("neuralcleave.cloud.health.detect_platform", return_value="render"):
        with patch("neuralcleave.cloud.health.cloud_env_vars", return_value={"RENDER": "true"}):
            result = runner.invoke(cli, ["cloud", "status"])
    assert result.exit_code == 0
    assert "render" in result.output


def test_cli_cloud_status_lists_env_vars():
    from neuralcleave.cli import cli

    runner = CliRunner()
    env = {"RAILWAY_ENVIRONMENT": "production", "RAILWAY_SERVICE_NAME": "gateway"}
    with patch("neuralcleave.cloud.health.detect_platform", return_value="railway"):
        with patch("neuralcleave.cloud.health.cloud_env_vars", return_value=env):
            result = runner.invoke(cli, ["cloud", "status"])
    assert "RAILWAY_ENVIRONMENT" in result.output
    assert "production" in result.output
