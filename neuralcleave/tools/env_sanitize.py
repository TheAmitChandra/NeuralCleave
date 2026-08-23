"""Shared environment-variable sanitization for tools that spawn a child
process (subprocess, a browser).

Round 4 (2026-08-21 gap analysis) §6.2 found this was `ShellTool`-only:
``BrowserAutomationTool`` launches a real Chromium subprocess via
Playwright with no equivalent scrubbing, so every provider API key/secret
currently in the gateway process's environment was passed straight
through to it — a real information-disclosure surface (crash dumps,
process listings, etc.) that ``ShellTool`` was already closed against.

Usage::

    from neuralcleave.tools.env_sanitize import sanitize_env

    env = sanitize_env()  # os.environ with sensitive keys stripped
"""

from __future__ import annotations

import os

# Environment variable name substrings that mark sensitive values to strip.
SENSITIVE_ENV_PATTERNS: tuple[str, ...] = (
    "API_KEY", "SECRET", "PASSWORD", "TOKEN", "PRIVATE", "CREDENTIAL",
    "ANTHROPIC", "GEMINI", "OPENAI", "DEEPSEEK", "ELEVENLABS", "FAL_KEY",
)


def sanitize_env(extra_patterns: tuple[str, ...] = ()) -> dict[str, str]:
    """Return ``os.environ`` with sensitive keys removed.

    Args:
        extra_patterns: Additional substrings (matched case-insensitively
                        against the key) to also strip, beyond
                        ``SENSITIVE_ENV_PATTERNS``.
    """
    patterns = tuple(p.upper() for p in (*SENSITIVE_ENV_PATTERNS, *extra_patterns))
    return {k: v for k, v in os.environ.items() if not any(p in k.upper() for p in patterns)}
