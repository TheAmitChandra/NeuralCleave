"""Cloud platform detection and Docker pre-flight checks."""

from __future__ import annotations

import os
import shutil
import subprocess

_RAILWAY_VARS = ("RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_NAME", "RAILWAY_PROJECT_ID")
_RENDER_VARS = ("RENDER", "RENDER_SERVICE_NAME", "RENDER_SERVICE_ID")
_FLY_VARS = ("FLY_APP_NAME", "FLY_REGION", "FLY_ALLOC_ID")
_HEROKU_VARS = ("DYNO", "HEROKU_APP_NAME")
_DIGITALOCEAN_VARS = ("DO_APP_ID", "DO_APP_NAME")

_ALL_PLATFORM_VARS = (
    _RAILWAY_VARS + _RENDER_VARS + _FLY_VARS + _HEROKU_VARS + _DIGITALOCEAN_VARS
)


def detect_platform() -> str | None:
    """Return the cloud platform name or ``None`` if running locally.

    Checks well-known environment variables injected by each platform's
    runtime.  Returns the *first* match in order: railway → render → fly →
    heroku → digitalocean.
    """
    if any(os.environ.get(v) for v in _RAILWAY_VARS):
        return "railway"
    if any(os.environ.get(v) for v in _RENDER_VARS):
        return "render"
    if any(os.environ.get(v) for v in _FLY_VARS):
        return "fly"
    if any(os.environ.get(v) for v in _HEROKU_VARS):
        return "heroku"
    if any(os.environ.get(v) for v in _DIGITALOCEAN_VARS):
        return "digitalocean"
    return None


def is_cloud() -> bool:
    """Return ``True`` when running inside a recognised cloud platform."""
    return detect_platform() is not None


def cloud_env_vars() -> dict[str, str]:
    """Return a snapshot of all recognised cloud platform env vars that are set."""
    return {k: v for k in _ALL_PLATFORM_VARS if (v := os.environ.get(k))}


def check_docker() -> tuple[bool, str]:
    """Return ``(available, detail)`` for the Docker CLI.

    *detail* is the version string on success, or an error description on
    failure.
    """
    if shutil.which("docker") is None:
        return False, "docker not found in PATH"
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or "docker --version returned non-zero exit"
    except subprocess.TimeoutExpired:
        return False, "docker --version timed out"
    except OSError as exc:
        return False, str(exc)


def check_compose() -> tuple[bool, str]:
    """Return ``(available, detail)`` for Docker Compose.

    Checks for the v2 plugin (``docker compose version``) first, then falls
    back to the v1 standalone binary (``docker-compose``).
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass

    if shutil.which("docker-compose") is None:
        return False, "neither 'docker compose' (plugin) nor 'docker-compose' found"

    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, result.stdout.strip() + " (v1 standalone)"
        return False, result.stderr.strip() or "docker-compose returned non-zero exit"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
