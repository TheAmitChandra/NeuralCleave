"""Voice layer: STT (faster-whisper), TTS (ElevenLabs/Kokoro/system), wake word, audio utils."""

from neuralcleave.voice.audio import (
    AudioChunkBuffer,
    AudioNormaliseError,
    detect_silence,
    normalise_to_pcm,
    normalise_to_wav,
    play_audio,
    trim_silence,
)
from neuralcleave.voice.continuous import ContinuousVoiceListener
from neuralcleave.voice.ptt import PushToTalkRecorder
from neuralcleave.voice.stt import WhisperSTT
from neuralcleave.voice.tts import TTSEngine
from neuralcleave.voice.vad import VADError, VoiceActivityDetector
from neuralcleave.voice.wake_word import WakeWordDetector

__all__ = [
    "AudioChunkBuffer",
    "AudioNormaliseError",
    "ContinuousVoiceListener",
    "PushToTalkRecorder",
    "TTSEngine",
    "VADError",
    "VoiceActivityDetector",
    "WakeWordDetector",
    "WhisperSTT",
    "detect_silence",
    "normalise_to_pcm",
    "normalise_to_wav",
    "play_audio",
    "trim_silence",
]
