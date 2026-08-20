"""Tests for neuralcleave.observability.host_metrics (P6, 2026-08-17 gap analysis)."""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

import neuralcleave.observability.host_metrics as host_metrics_module
from neuralcleave.observability.host_metrics import collect_host_metrics


def _fake_import_raising_for(module_name: str):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"No module named {module_name!r}")
        return real_import(name, *args, **kwargs)

    return fake_import


class TestPsutilNotInstalled:
    def test_returns_all_none_when_psutil_missing(self):
        with patch("builtins.__import__", side_effect=_fake_import_raising_for("psutil")):
            result = collect_host_metrics()

        assert result == {
            "cpu_percent": None,
            "memory_rss_bytes": None,
            "disk_usage_percent": None,
            "disk_free_bytes": None,
        }

    def test_does_not_raise(self):
        with patch("builtins.__import__", side_effect=_fake_import_raising_for("psutil")):
            collect_host_metrics()  # must not raise


class TestSuccessfulCollection:
    def _fake_psutil(self):
        fake_process = MagicMock()
        fake_process.cpu_percent.return_value = 4.5
        fake_process.memory_info.return_value = MagicMock(rss=123456)

        fake_disk = MagicMock(percent=42.0, free=999999)

        fake_psutil = MagicMock()
        fake_psutil.Process.return_value = fake_process
        fake_psutil.disk_usage.return_value = fake_disk
        return fake_psutil, fake_process

    def test_reports_cpu_and_memory(self, monkeypatch):
        monkeypatch.setattr(host_metrics_module, "_process", None)
        fake_psutil, _ = self._fake_psutil()

        with patch.dict("sys.modules", {"psutil": fake_psutil}):
            result = collect_host_metrics()

        assert result["cpu_percent"] == 4.5
        assert result["memory_rss_bytes"] == 123456.0

    def test_reports_disk_usage(self, monkeypatch):
        monkeypatch.setattr(host_metrics_module, "_process", None)
        fake_psutil, _ = self._fake_psutil()

        with patch.dict("sys.modules", {"psutil": fake_psutil}):
            result = collect_host_metrics()

        assert result["disk_usage_percent"] == 42.0
        assert result["disk_free_bytes"] == 999999.0

    def test_process_is_constructed_once_and_reused(self, monkeypatch):
        monkeypatch.setattr(host_metrics_module, "_process", None)
        fake_psutil, fake_process = self._fake_psutil()

        with patch.dict("sys.modules", {"psutil": fake_psutil}):
            collect_host_metrics()
            collect_host_metrics()

        assert fake_psutil.Process.call_count == 1
        # primed once on construction, then once per collect_host_metrics() call
        assert fake_process.cpu_percent.call_count == 3


class TestPartialFailure:
    def test_process_metrics_failure_still_returns_disk_metrics(self, monkeypatch):
        monkeypatch.setattr(host_metrics_module, "_process", None)
        fake_psutil = MagicMock()
        fake_psutil.Process.side_effect = Exception("no /proc access")
        fake_psutil.disk_usage.return_value = MagicMock(percent=10.0, free=500)

        with patch.dict("sys.modules", {"psutil": fake_psutil}):
            result = collect_host_metrics()

        assert result["cpu_percent"] is None
        assert result["memory_rss_bytes"] is None
        assert result["disk_usage_percent"] == 10.0

    def test_disk_metrics_failure_still_returns_process_metrics(self, monkeypatch):
        monkeypatch.setattr(host_metrics_module, "_process", None)
        fake_process = MagicMock()
        fake_process.cpu_percent.return_value = 1.0
        fake_process.memory_info.return_value = MagicMock(rss=42)
        fake_psutil = MagicMock()
        fake_psutil.Process.return_value = fake_process
        fake_psutil.disk_usage.side_effect = Exception("disk unavailable")

        with patch.dict("sys.modules", {"psutil": fake_psutil}):
            result = collect_host_metrics()

        assert result["cpu_percent"] == 1.0
        assert result["disk_usage_percent"] is None
