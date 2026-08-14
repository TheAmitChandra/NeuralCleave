"""Config tests for the 3 providers added in the P4 gap-closing pass:
OpenRouter, Azure OpenAI, and Amazon Bedrock — mirrors the existing pattern
in test_config_extended.py for the earlier 8-provider batch.
"""

from __future__ import annotations

import pytest

from neuralcleave.config import ModelsConfig, _parse_config


class TestModelsConfigDefaults:
    def test_openrouter_api_key_default(self):
        assert ModelsConfig().openrouter_api_key == ""

    def test_azure_api_key_default(self):
        assert ModelsConfig().azure_api_key == ""

    def test_azure_endpoint_default(self):
        assert ModelsConfig().azure_endpoint == ""

    def test_bedrock_region_default(self):
        assert ModelsConfig().bedrock_region == "us-east-1"


class TestParseConfig:
    def test_openrouter_api_key_parsed(self):
        cfg = _parse_config({"models": {"openrouter_api_key": "or-key-abc"}})
        assert cfg.models.openrouter_api_key == "or-key-abc"

    def test_azure_api_key_parsed(self):
        cfg = _parse_config({"models": {"azure_api_key": "az-key-xyz"}})
        assert cfg.models.azure_api_key == "az-key-xyz"

    def test_azure_endpoint_parsed(self):
        cfg = _parse_config({"models": {"azure_endpoint": "https://my-resource.openai.azure.com"}})
        assert cfg.models.azure_endpoint == "https://my-resource.openai.azure.com"

    def test_bedrock_region_parsed(self):
        cfg = _parse_config({"models": {"bedrock_region": "eu-west-1"}})
        assert cfg.models.bedrock_region == "eu-west-1"

    def test_bedrock_region_missing_defaults_to_us_east_1(self):
        cfg = _parse_config({"models": {"anthropic_api_key": "ant"}})
        assert cfg.models.bedrock_region == "us-east-1"

    def test_missing_keys_default_to_empty(self):
        cfg = _parse_config({"models": {"anthropic_api_key": "ant"}})
        assert cfg.models.openrouter_api_key == ""
        assert cfg.models.azure_api_key == ""
        assert cfg.models.azure_endpoint == ""

    def test_empty_models_section_all_new_keys_default(self):
        cfg = _parse_config({"models": {}})
        assert cfg.models.openrouter_api_key == ""
        assert cfg.models.azure_api_key == ""
        assert cfg.models.azure_endpoint == ""
        assert cfg.models.bedrock_region == "us-east-1"

    def test_all_new_fields_together(self):
        cfg = _parse_config(
            {
                "models": {
                    "openrouter_api_key": "or",
                    "azure_api_key": "az",
                    "azure_endpoint": "https://x.openai.azure.com",
                    "bedrock_region": "ap-south-1",
                }
            }
        )
        assert cfg.models.openrouter_api_key == "or"
        assert cfg.models.azure_api_key == "az"
        assert cfg.models.azure_endpoint == "https://x.openai.azure.com"
        assert cfg.models.bedrock_region == "ap-south-1"


class TestEnvResolution:
    """azure_endpoint and bedrock_region are not secrets and are passed through
    literally (no ENV: resolution) — only the two API keys support it."""

    def test_openrouter_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-from-env")
        cfg = _parse_config({"models": {"openrouter_api_key": "ENV:OPENROUTER_API_KEY"}})
        assert cfg.models.openrouter_api_key == "openrouter-from-env"

    def test_azure_api_key_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-from-env")
        cfg = _parse_config({"models": {"azure_api_key": "ENV:AZURE_OPENAI_API_KEY"}})
        assert cfg.models.azure_api_key == "azure-from-env"

    def test_missing_env_var_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _parse_config({"models": {"openrouter_api_key": "ENV:OPENROUTER_API_KEY"}})
        assert cfg.models.openrouter_api_key == ""
