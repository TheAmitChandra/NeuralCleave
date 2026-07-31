"""Tests for AgentRuntime._ptt attribute wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime
from neuralcleave.voice.ptt import PushToTalkRecorder


def _make_runtime(**kwargs) -> AgentRuntime:
    return AgentRuntime(pipeline=MagicMock(), session_mgr=MagicMock(), **kwargs)


class TestRuntimePttWiring:
    def test_ptt_none_by_default(self) -> None:
        rt = _make_runtime()
        assert rt._ptt is None

    def test_ptt_stored_when_provided(self) -> None:
        ptt = PushToTalkRecorder()
        rt = _make_runtime(ptt=ptt)
        assert rt._ptt is ptt

    def test_ptt_is_push_to_talk_recorder(self) -> None:
        ptt = PushToTalkRecorder(max_duration_s=20.0)
        rt = _make_runtime(ptt=ptt)
        assert isinstance(rt._ptt, PushToTalkRecorder)

    def test_ptt_mock_accepted(self) -> None:
        ptt = MagicMock()
        rt = _make_runtime(ptt=ptt)
        assert rt._ptt is ptt

    def test_ptt_max_duration_preserved(self) -> None:
        ptt = PushToTalkRecorder(max_duration_s=45.0)
        rt = _make_runtime(ptt=ptt)
        assert rt._ptt.max_duration_s == 45.0
