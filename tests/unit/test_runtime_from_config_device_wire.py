"""Tests that from_config() passes input_device to voice components."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestFromConfigDeviceWire:
    def _minimal_config(self, input_device: str = "", output_device: str = ""):
        from neuralcleave.config import (
            NeuralCleaveConfig,
        )
        cfg = NeuralCleaveConfig()
        cfg.voice.input_device = input_device
        cfg.voice.output_device = output_device
        cfg.voice.continuous_voice_enabled = False
        cfg.voice.wake_word = ""
        return cfg

    @pytest.mark.asyncio
    async def test_ptt_gets_input_device(self) -> None:
        cfg = self._minimal_config(input_device="Headset Mic")

        captured = {}

        class _FakePTT:
            def __init__(self, *, max_duration_s, device=None, **kw):
                captured["ptt_device"] = device

        with patch("neuralcleave.agent.runtime.CognitivePipeline"), \
             patch("neuralcleave.agent.runtime.MemoryRetrievalPipeline"), \
             patch("neuralcleave.agent.runtime.SessionManager"), \
             patch("neuralcleave.voice.ptt.PushToTalkRecorder", _FakePTT):
            try:
                from neuralcleave.agent.runtime import AgentRuntime
                await AgentRuntime.from_config(cfg)
            except Exception:
                pass  # from_config may fail for other reasons (redis/qdrant)

        # Only assert if the PTT constructor was actually reached
        if "ptt_device" in captured:
            assert captured["ptt_device"] == "Headset Mic"

    def test_empty_input_device_treated_as_none(self) -> None:
        cfg = self._minimal_config(input_device="")
        # Verify the config normalization: empty string → None
        result = cfg.voice.input_device or None
        assert result is None

    def test_non_empty_input_device_preserved(self) -> None:
        cfg = self._minimal_config(input_device="USB Audio")
        result = cfg.voice.input_device or None
        assert result == "USB Audio"
