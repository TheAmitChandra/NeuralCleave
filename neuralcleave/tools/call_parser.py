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

# Matches TOOL_CALL: followed by a JSON object on the same line.
_PATTERN = re.compile(r"^TOOL_CALL:\s*(\{.+\})\s*$", re.MULTILINE)


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
    match = _PATTERN.search(text)
    if not match:
        return None
    raw = match.group(0)
    try:
        payload = json.loads(match.group(1))
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
    return ParsedToolCall(name=name, arguments=arguments, raw=raw)
