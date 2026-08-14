"""Tests that AgentRuntime.from_config() forwards every ModelsConfig provider
key to the ModelRouter it builds.

Before this fix, from_config() only passed anthropic/gemini/deepseek/openai —
the 8 providers added in the earlier gap-closing pass (Mistral, xAI, Cohere,
Moonshot, Zhipu, Qwen, ERNIE, Doubao) were silently dropped even though
ModelsConfig parsed them fine from config.toml: a user relying purely on
config.toml (not the Settings UI runtime-apply endpoint) for one of those
keys would find it never actually reached the router. Fixed as part of
wiring the 3 new providers (OpenRouter, Azure, Bedrock) added alongside it,
since it's the exact same function and bug class.
"""

from __future__ import annotations

from neuralcleave.agent.runtime import AgentRuntime
from neuralcleave.config import NeuralCleaveConfig


class TestPreExistingProviderKeysNowWired:
    """The 8 providers from the earlier batch — previously dropped."""

    def test_mistral_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.mistral_api_key = "mistral-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._mistral_key == "mistral-key"

    def test_xai_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.xai_api_key = "xai-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._grok_key == "xai-key"

    def test_cohere_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.cohere_api_key = "cohere-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._cohere_key == "cohere-key"

    def test_moonshot_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.moonshot_api_key = "moonshot-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._moonshot_key == "moonshot-key"

    def test_zhipuai_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.zhipuai_api_key = "glm-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._glm_key == "glm-key"

    def test_dashscope_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.dashscope_api_key = "qwen-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._qwen_key == "qwen-key"

    def test_qianfan_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.qianfan_api_key = "ernie-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._ernie_key == "ernie-key"

    def test_ark_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.ark_api_key = "doubao-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._doubao_key == "doubao-key"


class TestNewProviderKeysWired:
    """OpenRouter, Azure, and Bedrock — added in this same pass."""

    def test_openrouter_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.openrouter_api_key = "or-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._openrouter_key == "or-key"

    def test_azure_api_key_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.azure_api_key = "az-key"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._azure_key == "az-key"

    def test_azure_endpoint_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.azure_endpoint = "https://my-resource.openai.azure.com"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._azure_endpoint == "https://my-resource.openai.azure.com"

    def test_bedrock_region_passed_to_router(self):
        cfg = NeuralCleaveConfig()
        cfg.models.bedrock_region = "eu-central-1"
        rt = AgentRuntime.from_config(cfg)
        assert rt._pipeline._router._bedrock_region == "eu-central-1"

    def test_bedrock_region_default_passed_through(self):
        rt = AgentRuntime.from_config(NeuralCleaveConfig())
        assert rt._pipeline._router._bedrock_region == "us-east-1"
