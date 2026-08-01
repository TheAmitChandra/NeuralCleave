"""Tests for input_device and output_device fields on VoiceConfig."""

from __future__ import annotations

from neuralcleave.config import VoiceConfig


class TestVoiceConfigDeviceFields:
    def test_input_device_default_empty(self) -> None:
        cfg = VoiceConfig()
        assert cfg.input_device == ""

    def test_output_device_default_empty(self) -> None:
        cfg = VoiceConfig()
        assert cfg.output_device == ""

    def test_input_device_assignable(self) -> None:
        cfg = VoiceConfig(input_device="Built-in Mic")
        assert cfg.input_device == "Built-in Mic"

    def test_output_device_assignable(self) -> None:
        cfg = VoiceConfig(output_device="USB Speaker")
        assert cfg.output_device == "USB Speaker"

    def test_both_fields_independent(self) -> None:
        cfg = VoiceConfig(input_device="mic_a", output_device="speaker_b")
        assert cfg.input_device == "mic_a"
        assert cfg.output_device == "speaker_b"
