"""Parse TOOL_CALL markers from LLM response text.

The LLM signals a tool call by placing exactly this on its own line:

    TOOL_CALL: {"name": "tool_name", "arguments": {"key": "value"}}

This module finds and decodes that marker so the pipeline can dispatch
the call to the registered tool.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Matches the opening of a TOOL_CALL line.  The JSON payload is decoded with
# json.JSONDecoder.raw_decode() so nested objects and multi-line arguments
# are handled correctly (the old single-line regex broke on wrapped JSON).
_MARKER = re.compile(r"^TOOL_CALL:\s*\{", re.MULTILINE)


@dataclass
class ParsedToolCall:
    """A decoded tool call extracted from LLM response text."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def parse(text: str) -> ParsedToolCall | None:
    """Return the first TOOL_CALL found in *text*, or None.

    Returns None when:
    - No TOOL_CALL marker is present
    - The JSON after TOOL_CALL: is malformed
    - The "name" field is missing or not a string
    """
    m = _MARKER.search(text)
    if not m:
        return None
    brace_pos = m.end() - 1  # position of the opening '{'
    try:
        decoder = json.JSONDecoder()
        payload, end_idx = decoder.raw_decode(text, brace_pos)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("name", "")
    if not isinstance(name, str) or not name:
        return None
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    raw = text[m.start():end_idx]
    return ParsedToolCall(name=name, arguments=arguments, raw=raw)
