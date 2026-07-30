"""Tests for TTSEngine._active_engine and _voice_id attributes added in Phase 3."""

from __future__ import annotations

from neuralcleave.voice.tts import TTSEngine


class TestActiveEngine:
    def test_default_active_engine_is_elevenlabs(self) -> None:
        t = TTSEngine()
        assert t._active_engine == "elevenlabs"

    def test_prefer_local_sets_kokoro(self) -> None:
        t = TTSEngine(prefer_local=True)
        assert t._active_engine == "kokoro"

    def test_explicit_tts_engine_overrides_prefer_local(self) -> None:
        t = TTSEngine(prefer_local=True, tts_engine="pyttsx3")
        assert t._active_engine == "pyttsx3"

    def test_explicit_tts_engine_elevenlabs(self) -> None:
        t = TTSEngine(tts_engine="elevenlabs")
        assert t._active_engine == "elevenlabs"

    def test_explicit_tts_engine_kokoro(self) -> None:
        t = TTSEngine(tts_engine="kokoro")
        assert t._active_engine == "kokoro"

    def test_active_engine_can_be_set(self) -> None:
        t = TTSEngine()
        t._active_engine = "pyttsx3"
        assert t._active_engine == "pyttsx3"

    def test_active_engine_empty_string_falls_to_elevenlabs(self) -> None:
        """Empty tts_engine string → defaults by prefer_local flag."""
        t = TTSEngine(prefer_local=False, tts_engine="")
        assert t._active_engine == "elevenlabs"


class TestVoiceIdProperty:
    def test_voice_id_getter_returns_el_voice(self) -> None:
        t = TTSEngine(elevenlabs_voice_id="abc123")
        assert t._voice_id == "abc123"

    def test_voice_id_getter_returns_default_when_not_set(self) -> None:
        t = TTSEngine()
        assert t._voice_id == TTSEngine.DEFAULT_ELEVENLABS_VOICE

    def test_voice_id_setter_updates_el_voice(self) -> None:
        t = TTSEngine()
        t._voice_id = "new-voice-id"
        assert t._el_voice == "new-voice-id"

    def test_voice_id_roundtrip(self) -> None:
        t = TTSEngine()
        t._voice_id = "roundtrip-voice"
        assert t._voice_id == "roundtrip-voice"

    def test_use_voice_and_voice_id_are_equivalent(self) -> None:
        t = TTSEngine()
        t.use_voice("voice-a")
        assert t._voice_id == "voice-a"
        t._voice_id = "voice-b"
        assert t._el_voice == "voice-b"
