"""Audio device enumeration for the voice pipeline.

Wraps ``sounddevice.query_devices()`` so the REST API and voice components
can list, filter, and resolve audio devices without coupling to sounddevice's
dict-based API directly.

Usage::

    from neuralcleave.voice.device_manager import list_input_devices, resolve_device

    for dev in list_input_devices():
        print(dev.index, dev.name)

    idx = resolve_device("Built-in Microphone", kind="input")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioDevice:
    """A single audio device as reported by the host OS."""

    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_sample_rate: float
    is_default_input: bool
    is_default_output: bool

    @property
    def is_input(self) -> bool:
        """``True`` if this device has at least one input channel."""
        return self.max_input_channels > 0

    @property
    def is_output(self) -> bool:
        """``True`` if this device has at least one output channel."""
        return self.max_output_channels > 0


def list_devices() -> list[AudioDevice]:
    """Return all audio devices reported by the host OS.

    Returns an empty list if ``sounddevice`` is not installed or the host
    has no audio hardware.
    """
    try:
        import sounddevice as sd  # type: ignore[import]
    except ImportError:
        logger.debug("device_manager: sounddevice not installed")
        return []

    try:
        raw = sd.query_devices()
        defaults = sd.default.device
        default_in = int(defaults[0]) if isinstance(defaults, (list, tuple)) else -1
        default_out = int(defaults[1]) if isinstance(defaults, (list, tuple)) else -1
    except Exception as exc:
        logger.warning("device_manager.list_devices failed: %s", exc)
        return []

    devices: list[AudioDevice] = []
    for idx, info in enumerate(raw):
        devices.append(
            AudioDevice(
                index=idx,
                name=str(info.get("name", "")),
                max_input_channels=int(info.get("max_input_channels", 0)),
                max_output_channels=int(info.get("max_output_channels", 0)),
                default_sample_rate=float(info.get("default_samplerate", 44100.0)),
                is_default_input=(idx == default_in),
                is_default_output=(idx == default_out),
            )
        )
    return devices


def list_input_devices() -> list[AudioDevice]:
    """Return only devices that have at least one input channel."""
    return [d for d in list_devices() if d.is_input]


def list_output_devices() -> list[AudioDevice]:
    """Return only devices that have at least one output channel."""
    return [d for d in list_devices() if d.is_output]


def get_default_input() -> AudioDevice | None:
    """Return the current system default input device, or ``None``."""
    for d in list_devices():
        if d.is_default_input and d.is_input:
            return d
    return None


def get_default_output() -> AudioDevice | None:
    """Return the current system default output device, or ``None``."""
    for d in list_devices():
        if d.is_default_output and d.is_output:
            return d
    return None


def find_device(name: str, *, kind: str = "input") -> AudioDevice | None:
    """Find the first device whose name contains *name* (case-insensitive).

    Args:
        name: Substring to match against device names.
        kind: ``"input"`` to restrict to input devices, ``"output"`` for
              output, or ``"any"`` for no restriction.

    Returns:
        The first matching :class:`AudioDevice`, or ``None``.
    """
    name_lower = name.lower()
    if kind == "input":
        candidates = list_input_devices()
    elif kind == "output":
        candidates = list_output_devices()
    else:
        candidates = list_devices()
    for d in candidates:
        if name_lower in d.name.lower():
            return d
    return None


def resolve_device(
    name_or_index: str | int | None,
    *,
    kind: str = "input",
) -> int | None:
    """Resolve a device name or index to a sounddevice device index.

    *name_or_index* may be:

    - ``None`` or ``""`` → ``None`` (sounddevice uses the system default)
    - An ``int``         → returned as-is (treated as a direct device index)
    - A ``str``          → partial case-insensitive name match

    Returns the resolved device index, or ``None`` to signal "use default".
    Logs a warning and returns ``None`` if a name cannot be resolved.
    """
    if name_or_index is None or name_or_index == "":
        return None
    if isinstance(name_or_index, int):
        return name_or_index
    device = find_device(name_or_index, kind=kind)
    if device is None:
        logger.warning(
            "device_manager.resolve_device: no %s device matching %r — using default",
            kind,
            name_or_index,
        )
        return None
    return device.index
