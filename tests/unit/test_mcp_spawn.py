"""Tests for McpServerProcess lifecycle management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from neuralcleave.mcp.spawn import McpServerProcess


class TestMcpServerProcess:
    def test_initial_state_not_running(self) -> None:
        proc = McpServerProcess()
        assert proc.is_running is False

    def test_initial_pid_is_none(self) -> None:
        proc = McpServerProcess()
        assert proc.pid is None

    def test_status_returns_not_running_initially(self) -> None:
        proc = McpServerProcess()
        status = proc.status()
        assert status["running"] is False
        assert status["pid"] is None

    def test_kill_when_not_running_returns_false(self) -> None:
        proc = McpServerProcess()
        assert proc.kill() is False

    def test_spawn_starts_subprocess(self) -> None:
        proc = McpServerProcess()
        mock_popen = MagicMock()
        mock_popen.pid = 12345
        mock_popen.poll.return_value = None  # still running

        with patch("neuralcleave.mcp.spawn.subprocess.Popen", return_value=mock_popen):
            pid = proc.spawn()

        assert pid == 12345
        assert proc.is_running is True

    def test_spawn_twice_returns_same_pid(self) -> None:
        proc = McpServerProcess()
        mock_popen = MagicMock()
        mock_popen.pid = 99
        mock_popen.poll.return_value = None

        with patch("neuralcleave.mcp.spawn.subprocess.Popen", return_value=mock_popen) as mock:
            proc.spawn()
            second_pid = proc.spawn()

        mock.assert_called_once()
        assert second_pid == 99

    def test_kill_terminates_running_process(self) -> None:
        proc = McpServerProcess()
        mock_popen = MagicMock()
        mock_popen.pid = 42
        mock_popen.poll.return_value = None

        with patch("neuralcleave.mcp.spawn.subprocess.Popen", return_value=mock_popen):
            proc.spawn()

        killed = proc.kill()
        assert killed is True
        mock_popen.terminate.assert_called_once()

    def test_after_kill_is_not_running(self) -> None:
        proc = McpServerProcess()
        mock_popen = MagicMock()
        mock_popen.pid = 11
        mock_popen.poll.return_value = None

        with patch("neuralcleave.mcp.spawn.subprocess.Popen", return_value=mock_popen):
            proc.spawn()

        proc.kill()
        assert proc.is_running is False
        assert proc.pid is None

    def test_status_shows_running_after_spawn(self) -> None:
        proc = McpServerProcess()
        mock_popen = MagicMock()
        mock_popen.pid = 555
        mock_popen.poll.return_value = None

        with patch("neuralcleave.mcp.spawn.subprocess.Popen", return_value=mock_popen):
            proc.spawn()

        status = proc.status()
        assert status["running"] is True
        assert status["pid"] == 555
