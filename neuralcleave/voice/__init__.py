"""Voice layer: STT (faster-whisper), TTS (ElevenLabs/Kokoro/system), wake word, audio utils."""

from neuralcleave.voice.audio import (
    AudioNormaliseError,
    detect_silence,
    normalise_to_pcm,
    normalise_to_wav,
    trim_silence,
)
from neuralcleave.voice.continuous import ContinuousVoiceListener
from neuralcleave.voice.stt import WhisperSTT
from neuralcleave.voice.tts import TTSEngine
from neuralcleave.voice.vad import VADError, VoiceActivityDetector
from neuralcleave.voice.wake_word import WakeWordDetector

__all__ = [
    "AudioNormaliseError",
    "ContinuousVoiceListener",
    "TTSEngine",
    "VADError",
    "VoiceActivityDetector",
    "WakeWordDetector",
    "WhisperSTT",
    "detect_silence",
    "normalise_to_pcm",
    "normalise_to_wav",
    "trim_silence",
]
