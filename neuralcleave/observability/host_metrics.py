"""Host resource metrics — CPU/memory/disk usage for the running process and
machine, via ``psutil``.

P6 of the 2026-08-17 gap analysis: ``/api/v1/status`` previously reported
only uptime and session count, with no CPU/memory/disk visibility at all —
a solo operator had no first-party way to notice "the gateway is quietly
eating all the RAM" short of an OS-level tool.

Usage::

    from neuralcleave.observability.host_metrics import collect_host_metrics

    snapshot = collect_host_metrics()
    # {"cpu_percent": 3.2, "memory_rss_bytes": 84213760,
    #  "disk_usage_percent": 41.7, "disk_free_bytes": 128849018880}
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Cached across calls so cpu_percent() can report a real interval-based
# reading — psutil's documented pattern: the first call after a Process is
# constructed always returns 0.0 (no prior sample to diff against), so we
# keep one Process instance alive for the life of this module and prime its
# baseline once, here, rather than on every collect_host_metrics() call.
_process: Any | None = None


def _get_process() -> Any | None:
    global _process
    import psutil

    if _process is None:
        _process = psutil.Process(os.getpid())
        _process.cpu_percent(interval=None)  # prime baseline; first read is always 0.0
    return _process


def collect_host_metrics() -> dict[str, float | None]:
    """Return a snapshot of process CPU%, process RSS bytes, and disk usage
    for the state directory's filesystem.

    Never raises — returns ``None`` values (not zeroes, so callers can tell
    "unavailable" from "genuinely zero") if ``psutil`` isn't installed or a
    read fails for any reason (e.g. sandboxed environments that restrict
    ``/proc`` access). ``cpu_percent`` reflects usage since the *previous*
    call in this process (0.0 on the very first call after startup — that's
    a psutil limitation, not a bug).
    """
    result: dict[str, float | None] = {
        "cpu_percent": None,
        "memory_rss_bytes": None,
        "disk_usage_percent": None,
        "disk_free_bytes": None,
    }
    try:
        import psutil
    except ImportError:
        logger.debug("host_metrics: psutil not installed")
        return result

    try:
        process = _get_process()
        result["cpu_percent"] = process.cpu_percent(interval=None)
        result["memory_rss_bytes"] = float(process.memory_info().rss)
    except Exception as exc:
        logger.debug("host_metrics: process metrics unavailable: %s", exc)

    try:
        state_dir = os.path.expanduser("~/.neuralcleave")
        usage = psutil.disk_usage(state_dir if os.path.isdir(state_dir) else os.path.expanduser("~"))
        result["disk_usage_percent"] = float(usage.percent)
        result["disk_free_bytes"] = float(usage.free)
    except Exception as exc:
        logger.debug("host_metrics: disk metrics unavailable: %s", exc)

    return result
