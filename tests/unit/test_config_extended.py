"""Extended config tests — covers the 8 new LLM provider keys and gateway api_key
added to ModelsConfig / GatewayConfig after PR #66 (new providers) and the
gateway auth feature.
"""

from __future__ import annotations

import pytest

from cortexflow_ai.config import (
    GatewayConfig,
    ModelsConfig,
    _parse_config,
)

# ---------------------------------------------------------------------------
# ModelsConfig — new provider key fields exist and default to ""
# ---------------------------------------------------------------------------


class TestModelsConfigNewProviderDefaults:
    def test_mistral_api_key_default(self):
        assert ModelsConfig().mistral_api_key == ""

    def test_xai_api_key_default(self):
        assert ModelsConfig().xai_api_key == ""

    def test_cohere_api_key_default(self):
        assert ModelsConfig().cohere_api_key == ""

    def test_moonshot_api_key_default(self):
        assert ModelsConfig().moonshot_api_key == ""

    def test_zhipuai_api_key_default(self):
        assert ModelsConfig().zhipuai_api_key == ""

    def test_dashscope_api_key_default(self):
        assert ModelsConfig().dashscope_api_key == ""

    def test_qianfan_api_key_default(self):
        assert ModelsConfig().qianfan_api_key == ""

    def test_ark_api_key_default(self):
        assert ModelsConfig().ark_api_key == ""


# ---------------------------------------------------------------------------
# _parse_config — new provider keys parsed correctly from TOML dict
# ---------------------------------------------------------------------------


class TestParseConfigNewProviderKeys:
    def test_mistral_api_key_parsed(self):
        cfg = _parse_config({"models": {"mistral_api_key": "mistral-key-abc"}})
        assert cfg.models.mistral_api_key == "mistral-key-abc"

    def test_xai_api_key_parsed(self):
        cfg = _parse_config({"models": {"xai_api_key": "xai-grok-key"}})
        assert cfg.models.xai_api_key == "xai-grok-key"

    def test_cohere_api_key_parsed(self):
        cfg = _parse_config({"models": {"cohere_api_key": "cohere-xyz"}})
        assert cfg.models.cohere_api_key == "cohere-xyz"

    def test_moonshot_api_key_parsed(self):
        cfg = _parse_config({"models": {"moonshot_api_key": "kimi-moon-key"}})
        assert cfg.models.moonshot_api_key == "kimi-moon-key"

    def test_zhipuai_api_key_parsed(self):
        cfg = _parse_config({"models": {"zhipuai_api_key": "glm-key-zzz"}})
        assert cfg.models.zhipuai_api_key == "glm-key-zzz"

    def test_dashscope_api_key_parsed(self):
        cfg = _parse_config({"models": {"dashscope_api_key": "qwen-ds-key"}})
        assert cfg.models.dashscope_api_key == "qwen-ds-key"

    def test_qianfan_api_key_parsed(self):
        cfg = _parse_config({"models": {"qianfan_api_key": "ernie-qf-key"}})
        assert cfg.models.qianfan_api_key == "ernie-qf-key"

    def test_ark_api_key_parsed(self):
        cfg = _parse_config({"models": {"ark_api_key": "doubao-ark-key"}})
        assert cfg.models.ark_api_key == "doubao-ark-key"

    def test_all_new_keys_together(self):
        cfg = _parse_config({
            "models": {
                "mistral_api_key": "m",
                "xai_api_key": "x",
                "cohere_api_key": "c",
                "moonshot_api_key": "mo",
                "zhipuai_api_key": "z",
                "dashscope_api_key": "d",
                "qianfan_api_key": "q",
                "ark_api_key": "a",
            }
        })
        assert cfg.models.mistral_api_key == "m"
        assert cfg.models.xai_api_key == "x"
        assert cfg.models.cohere_api_key == "c"
        assert cfg.models.moonshot_api_key == "mo"
        assert cfg.models.zhipuai_api_key == "z"
        assert cfg.models.dashscope_api_key == "d"
        assert cfg.models.qianfan_api_key == "q"
        assert cfg.models.ark_api_key == "a"

    def test_missing_new_keys_default_to_empty(self):
        cfg = _parse_config({"models": {"anthropic_api_key": "ant"}})
        assert cfg.models.mistral_api_key == ""
        assert cfg.models.ark_api_key == ""

    def test_empty_models_section_all_new_keys_default(self):
        cfg = _parse_config({"models": {}})
        for key in (
            "mistral_api_key", "xai_api_key", "cohere_api_key",
            "moonshot_api_key", "zhipuai_api_key", "dashscope_api_key",
            "qianfan_api_key", "ark_api_key",
        ):
            assert getattr(cfg.models, key) == "", f"{key} should default to ''"


# ---------------------------------------------------------------------------
# ENV: resolution for new provider keys
# ---------------------------------------------------------------------------


class TestNewProviderKeysEnvResolution:
    def test_mistral_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "mistral-from-env")
        cfg = _parse_config({"models": {"mistral_api_key": "ENV:MISTRAL_API_KEY"}})
        assert cfg.models.mistral_api_key == "mistral-from-env"

    def test_xai_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("XAI_API_KEY", "xai-from-env")
        cfg = _parse_config({"models": {"xai_api_key": "ENV:XAI_API_KEY"}})
        assert cfg.models.xai_api_key == "xai-from-env"

    def test_cohere_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("COHERE_API_KEY", "cohere-from-env")
        cfg = _parse_config({"models": {"cohere_api_key": "ENV:COHERE_API_KEY"}})
        assert cfg.models.cohere_api_key == "cohere-from-env"

    def test_moonshot_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MOONSHOT_API_KEY", "moon-from-env")
        cfg = _parse_config({"models": {"moonshot_api_key": "ENV:MOONSHOT_API_KEY"}})
        assert cfg.models.moonshot_api_key == "moon-from-env"

    def test_zhipuai_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ZHIPUAI_API_KEY", "glm-from-env")
        cfg = _parse_config({"models": {"zhipuai_api_key": "ENV:ZHIPUAI_API_KEY"}})
        assert cfg.models.zhipuai_api_key == "glm-from-env"

    def test_dashscope_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "qwen-from-env")
        cfg = _parse_config({"models": {"dashscope_api_key": "ENV:DASHSCOPE_API_KEY"}})
        assert cfg.models.dashscope_api_key == "qwen-from-env"

    def test_qianfan_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("QIANFAN_API_KEY", "ernie-from-env")
        cfg = _parse_config({"models": {"qianfan_api_key": "ENV:QIANFAN_API_KEY"}})
        assert cfg.models.qianfan_api_key == "ernie-from-env"

    def test_ark_env_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ARK_API_KEY", "doubao-from-env")
        cfg = _parse_config({"models": {"ark_api_key": "ENV:ARK_API_KEY"}})
        assert cfg.models.ark_api_key == "doubao-from-env"

    def test_missing_env_var_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        cfg = _parse_config({"models": {"mistral_api_key": "ENV:MISTRAL_API_KEY"}})
        assert cfg.models.mistral_api_key == ""


# ---------------------------------------------------------------------------
# GatewayConfig — api_key field
# ---------------------------------------------------------------------------


class TestGatewayConfigApiKey:
    def test_api_key_default_is_empty(self):
        assert GatewayConfig().api_key == ""

    def test_api_key_set_inline(self):
        gw = GatewayConfig(api_key="my-secret")
        assert gw.api_key == "my-secret"

    def test_api_key_parsed_from_toml(self):
        cfg = _parse_config({"gateway": {"api_key": "toml-key"}})
        assert cfg.gateway.api_key == "toml-key"

    def test_api_key_empty_string_parsed(self):
        cfg = _parse_config({"gateway": {"api_key": ""}})
        assert cfg.gateway.api_key == ""

    def test_api_key_resolves_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GATEWAY_API_KEY", "from-env-gw")
        cfg = _parse_config({"gateway": {"api_key": "ENV:GATEWAY_API_KEY"}})
        assert cfg.gateway.api_key == "from-env-gw"

    def test_api_key_missing_env_is_empty(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
        cfg = _parse_config({"gateway": {"api_key": "ENV:GATEWAY_API_KEY"}})
        assert cfg.gateway.api_key == ""

    def test_existing_gateway_fields_unaffected(self):
        cfg = _parse_config({"gateway": {"port": 9000, "bind": "0.0.0.0", "api_key": "k"}})
        assert cfg.gateway.port == 9000
        assert cfg.gateway.bind == "0.0.0.0"
        assert cfg.gateway.api_key == "k"
