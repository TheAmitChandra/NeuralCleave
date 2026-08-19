"""Config tests for the 3 providers added in the P3 gap-closing pass (round 3,
2026-08-17 analysis): Groq, Together AI, and Fireworks AI — mirrors the
existing pattern in test_config_openrouter_azure_bedrock.py.
"""

from __future__ import annotations

import pytest

from neuralcleave.config import ModelsConfig, _parse_config


class TestModelsConfigDefaults:
    def test_groq_api_key_default(self):
        assert ModelsConfig().groq_api_key == ""

    def test_together_api_key_default(self):
        assert ModelsConfig().together_api_key == ""

    def test_fireworks_api_key_default(self):
        assert ModelsConfig().fireworks_api_key == ""


class TestParseConfig:
    def test_groq_api_key_parsed(self):
        cfg = _parse_config({"models": {"groq_api_key": "groq-key-abc"}})
        assert cfg.models.groq_api_key == "groq-key-abc"

    def test_together_api_key_parsed(self):
        cfg = _parse_config({"models": {"together_api_key": "tog-key-xyz"}})
        assert cfg.models.together_api_key == "tog-key-xyz"

    def test_fireworks_api_key_parsed(self):
        cfg = _parse_config({"models": {"fireworks_api_key": "fw-key-123"}})
        assert cfg.models.fireworks_api_key == "fw-key-123"

    def test_missing_keys_default_to_empty(self):
        cfg = _parse_config({"models": {"anthropic_api_key": "ant"}})
        assert cfg.models.groq_api_key == ""
        assert cfg.models.together_api_key == ""
        assert cfg.models.fireworks_api_key == ""

    def test_empty_models_section_all_new_keys_default(self):
        cfg = _parse_config({"models": {}})
        assert cfg.models.groq_api_key == ""
        assert cfg.models.together_api_key == ""
        assert cfg.models.fireworks_api_key == ""

    def test_all_new_fields_together(self):
        cfg = _parse_config(
            {
                "models": {
                    "groq_api_key": "g",
                    "together_api_key": "t",
                    "fireworks_api_key": "f",
                }
            }
        )
        assert cfg.models.groq_api_key == "g"
        assert cfg.models.together_api_key == "t"
        assert cfg.models.fireworks_api_key == "f"


class TestEnvResolution:
    def test_groq_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GROQ_API_KEY", "groq-from-env")
        cfg = _parse_config({"models": {"groq_api_key": "ENV:GROQ_API_KEY"}})
        assert cfg.models.groq_api_key == "groq-from-env"

    def test_together_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TOGETHER_API_KEY", "together-from-env")
        cfg = _parse_config({"models": {"together_api_key": "ENV:TOGETHER_API_KEY"}})
        assert cfg.models.together_api_key == "together-from-env"

    def test_fireworks_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FIREWORKS_API_KEY", "fireworks-from-env")
        cfg = _parse_config({"models": {"fireworks_api_key": "ENV:FIREWORKS_API_KEY"}})
        assert cfg.models.fireworks_api_key == "fireworks-from-env"

    def test_missing_env_var_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        cfg = _parse_config({"models": {"groq_api_key": "ENV:GROQ_API_KEY"}})
        assert cfg.models.groq_api_key == ""
