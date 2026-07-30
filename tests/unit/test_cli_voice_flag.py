"""Tests for neuralcleave start --voice flag."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from neuralcleave.cli import cli


def _make_cfg() -> MagicMock:
    cfg = MagicMock()
    cfg.gateway.bind = "127.0.0.1"
    cfg.gateway.port = 7432
    cfg.voice.continuous_voice_enabled = False
    return cfg


class TestVoiceFlag:
    def test_voice_flag_sets_continuous_enabled(self) -> None:
        """--voice must set voice.continuous_voice_enabled before calling run()."""
        cfg = _make_cfg()
        captured: dict[str, object] = {}

        def fake_run(c):
            captured["cfg"] = c

        runner = CliRunner()
        with patch("neuralcleave.config.load_config", return_value=cfg), \
             patch("neuralcleave.cli._check_port_in_use", return_value=False), \
             patch("neuralcleave.gateway.main.run", side_effect=fake_run):
            runner.invoke(cli, ["start", "--voice"])

        assert cfg.voice.continuous_voice_enabled is True

    def test_no_voice_flag_leaves_config_unchanged(self) -> None:
        """Omitting --voice must not touch continuous_voice_enabled."""
        cfg = _make_cfg()

        def fake_run(c):
            pass

        runner = CliRunner()
        with patch("neuralcleave.config.load_config", return_value=cfg), \
             patch("neuralcleave.cli._check_port_in_use", return_value=False), \
             patch("neuralcleave.gateway.main.run", side_effect=fake_run):
            runner.invoke(cli, ["start"])

        assert cfg.voice.continuous_voice_enabled is False

    def test_voice_flag_port_already_in_use_exits_early(self) -> None:
        """Port conflict must abort before setting voice config."""
        cfg = _make_cfg()
        runner = CliRunner()
        with patch("neuralcleave.config.load_config", return_value=cfg), \
             patch("neuralcleave.cli._check_port_in_use", return_value=True):
            result = runner.invoke(cli, ["start", "--voice"])
        assert result.exit_code == 0
        assert "already in use" in result.output

    def test_voice_flag_background_includes_flag_in_spawn_cmd(self) -> None:
        """--voice --background must pass --voice to the spawned subprocess."""
        cfg = _make_cfg()
        spawned_cmd: list[str] = []

        def fake_spawn(cmd):
            spawned_cmd.extend(cmd)
            return 99999

        runner = CliRunner()
        with patch("neuralcleave.config.load_config", return_value=cfg), \
             patch("neuralcleave.cli._check_port_in_use", return_value=False), \
             patch("neuralcleave.cli._pidfile_path", return_value=MagicMock(
                 parent=MagicMock(), write_text=MagicMock()
             )), \
             patch("neuralcleave.cli._read_pidfile", return_value=None), \
             patch("neuralcleave.cli._spawn_background", side_effect=fake_spawn):
            runner.invoke(cli, ["start", "--background", "--voice"])

        assert "--voice" in spawned_cmd
