"""Unit tests for neuralcleave.tools.env_sanitize — the shared subprocess
env-scrubbing helper (round 4 §6.2 secrets-split follow-up, extracted from
ShellTool so BrowserAutomationTool can use the exact same protection).

See test_tools_shell.py for ShellTool's own sanitize_env-through-_sanitize_env
regression tests, which continue to exercise this module indirectly.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from neuralcleave.tools.env_sanitize import SENSITIVE_ENV_PATTERNS, sanitize_env


def test_strips_api_key() -> None:
    with patch.dict(os.environ, {"MY_API_KEY": "secret123"}):
        env = sanitize_env()
    assert "MY_API_KEY" not in env


def test_strips_token() -> None:
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-secret"}):
        env = sanitize_env()
    assert "SLACK_BOT_TOKEN" not in env


def test_strips_fal_key() -> None:
    """FAL_KEY doesn't end in _API_KEY like most provider keys, so it
    needs its own explicit pattern entry."""
    with patch.dict(os.environ, {"FAL_KEY": "fal-secret"}):
        env = sanitize_env()
    assert "FAL_KEY" not in env


def test_preserves_non_sensitive() -> None:
    with patch.dict(os.environ, {"HOME": "/home/user", "PATH": "/usr/bin"}):
        env = sanitize_env()
    assert "HOME" in env
    assert "PATH" in env


def test_matching_is_case_insensitive() -> None:
    with patch.dict(os.environ, {"my_secret_value": "x"}):
        env = sanitize_env()
    assert "my_secret_value" not in env


def test_extra_patterns_are_also_stripped() -> None:
    with patch.dict(os.environ, {"CUSTOM_VENDOR_KEY": "x", "PATH": "/usr/bin"}):
        env = sanitize_env(extra_patterns=("CUSTOM_VENDOR",))
    assert "CUSTOM_VENDOR_KEY" not in env
    assert "PATH" in env


def test_extra_patterns_do_not_affect_the_default_list() -> None:
    with patch.dict(os.environ, {"MY_API_KEY": "secret123"}):
        env = sanitize_env(extra_patterns=("SOMETHING_ELSE",))
    assert "MY_API_KEY" not in env  # still stripped by the base list


def test_sensitive_patterns_is_a_public_stable_list() -> None:
    assert "API_KEY" in SENSITIVE_ENV_PATTERNS
    assert "TOKEN" in SENSITIVE_ENV_PATTERNS
