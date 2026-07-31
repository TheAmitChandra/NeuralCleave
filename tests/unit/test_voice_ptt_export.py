"""Tests for PushToTalkRecorder export from the voice package."""

from __future__ import annotations

from neuralcleave.voice import PushToTalkRecorder
from neuralcleave.voice.ptt import PushToTalkRecorder as _PttDirect


class TestPttExport:
    def test_push_to_talk_recorder_importable_from_voice(self) -> None:
        assert PushToTalkRecorder is not None

    def test_exported_class_is_same_as_module_class(self) -> None:
        assert PushToTalkRecorder is _PttDirect

    def test_push_to_talk_recorder_in_all(self) -> None:
        from neuralcleave.voice import __all__
        assert "PushToTalkRecorder" in __all__

    def test_instantiable_from_package_import(self) -> None:
        ptt = PushToTalkRecorder(max_duration_s=10.0)
        assert ptt.max_duration_s == 10.0
