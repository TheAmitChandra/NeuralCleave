"""Tests for ModelRouter.from_config() — the single config->kwarg mapping
extracted from AgentRuntime.from_config() (P6, 2026-08-17 gap analysis).

See test_agent_runtime_provider_keys.py for the AgentRuntime-level
regression guard this refactor had to keep passing unchanged.
"""

from __future__ import annotations

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.models.router import ModelRouter


class TestFromConfigWiresEveryProviderKey:
    def test_anthropic_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.anthropic_api_key = "anthropic-key"
        router = ModelRouter.from_config(cfg)
        assert router._anthropic_key == "anthropic-key"

    def test_gemini_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.gemini_api_key = "gemini-key"
        router = ModelRouter.from_config(cfg)
        assert router._gemini_key == "gemini-key"

    def test_deepseek_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.deepseek_api_key = "deepseek-key"
        router = ModelRouter.from_config(cfg)
        assert router._deepseek_key == "deepseek-key"

    def test_openai_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.openai_api_key = "openai-key"
        router = ModelRouter.from_config(cfg)
        assert router._openai_key == "openai-key"

    def test_ollama_base_url(self):
        cfg = NeuralCleaveConfig()
        cfg.models.ollama_base_url = "http://custom:1234"
        router = ModelRouter.from_config(cfg)
        assert router._ollama_url == "http://custom:1234"

    def test_mistral_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.mistral_api_key = "mistral-key"
        router = ModelRouter.from_config(cfg)
        assert router._mistral_key == "mistral-key"

    def test_xai_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.xai_api_key = "xai-key"
        router = ModelRouter.from_config(cfg)
        assert router._grok_key == "xai-key"

    def test_cohere_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.cohere_api_key = "cohere-key"
        router = ModelRouter.from_config(cfg)
        assert router._cohere_key == "cohere-key"

    def test_moonshot_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.moonshot_api_key = "moonshot-key"
        router = ModelRouter.from_config(cfg)
        assert router._moonshot_key == "moonshot-key"

    def test_zhipu_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.zhipuai_api_key = "zhipu-key"
        router = ModelRouter.from_config(cfg)
        assert router._glm_key == "zhipu-key"

    def test_qwen_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.dashscope_api_key = "qwen-key"
        router = ModelRouter.from_config(cfg)
        assert router._qwen_key == "qwen-key"

    def test_ernie_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.qianfan_api_key = "ernie-key"
        router = ModelRouter.from_config(cfg)
        assert router._ernie_key == "ernie-key"

    def test_doubao_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.ark_api_key = "doubao-key"
        router = ModelRouter.from_config(cfg)
        assert router._doubao_key == "doubao-key"

    def test_openrouter_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.openrouter_api_key = "openrouter-key"
        router = ModelRouter.from_config(cfg)
        assert router._openrouter_key == "openrouter-key"

    def test_azure_key_and_endpoint(self):
        cfg = NeuralCleaveConfig()
        cfg.models.azure_api_key = "azure-key"
        cfg.models.azure_endpoint = "https://x.openai.azure.com"
        router = ModelRouter.from_config(cfg)
        assert router._azure_key == "azure-key"
        assert router._azure_endpoint == "https://x.openai.azure.com"

    def test_bedrock_region(self):
        cfg = NeuralCleaveConfig()
        cfg.models.bedrock_region = "eu-west-1"
        router = ModelRouter.from_config(cfg)
        assert router._bedrock_region == "eu-west-1"

    def test_groq_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.groq_api_key = "groq-key"
        router = ModelRouter.from_config(cfg)
        assert router._groq_key == "groq-key"

    def test_together_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.together_api_key = "together-key"
        router = ModelRouter.from_config(cfg)
        assert router._together_key == "together-key"

    def test_fireworks_key(self):
        cfg = NeuralCleaveConfig()
        cfg.models.fireworks_api_key = "fireworks-key"
        router = ModelRouter.from_config(cfg)
        assert router._fireworks_key == "fireworks-key"

    def test_web_search_enabled(self):
        cfg = NeuralCleaveConfig()
        cfg.models.web_search_enabled = True
        router = ModelRouter.from_config(cfg)
        assert router._web_search is True


class TestFromConfigReturnsModelRouterInstance:
    def test_returns_model_router(self):
        router = ModelRouter.from_config(NeuralCleaveConfig())
        assert isinstance(router, ModelRouter)
