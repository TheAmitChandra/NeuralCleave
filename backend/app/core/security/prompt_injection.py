"""Prompt Injection Defense — multi-layer detection and sanitisation.

Threat model:
    An attacker embeds adversarial instructions inside:
    - user-provided input fields
    - tool output / web-scraped content
    - memory retrieved from external sources
    - agent-to-agent messages

Detection layers (applied in order, cheapest first):
    1. Pattern matching  — regex patterns for known injection signatures
    2. Heuristic scoring — statistical signals (instruction density, role-play markers)
    3. LLM-based check  — optional secondary LLM call for ambiguous inputs

Architecture:
    ``PromptInjectionDetector`` — stateless, can be imported and called anywhere.
    ``ScanResult``              — dataclass returned by every scan.
    ``sanitise()``              — strips / neutralises detected patterns.
    ``check_tool_output()``     — convenience wrapper for scanning tool results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

# Each entry: (pattern_name, compiled_regex)
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Classic role-reassignment
    ("role_reassignment", re.compile(
        r"\b(ignore|forget|disregard|override)\b.{0,40}\b(previous|prior|above|earlier|all)\b.{0,40}\b(instructions?|rules?|directives?|constraints?|guidelines?)\b",
        re.IGNORECASE | re.DOTALL,
    )),
    # "You are now" persona hijack
    ("persona_hijack", re.compile(
        r"\byou\s+are\s+now\b.{0,60}\b(a|an|the)\b",
        re.IGNORECASE | re.DOTALL,
    )),
    # "Act as" / "pretend to be"
    ("act_as", re.compile(
        r"\b(act\s+as|pretend\s+(to\s+be|you\s+are)|roleplay\s+as|simulate\s+being)\b",
        re.IGNORECASE,
    )),
    # System prompt / hidden instruction markers
    ("system_marker", re.compile(
        r"(<\|system\|>|<<SYS>>|\[INST\]|<\|im_start\|>system|###\s*System\s*:)",
        re.IGNORECASE,
    )),
    # "Do anything now" / DAN-style
    ("dan_style", re.compile(
        r"\b(DAN|jailbreak|do\s+anything\s+now|without\s+restrictions?|no\s+limits?|bypass)\b",
        re.IGNORECASE,
    )),
    # Credential / secret extraction
    ("credential_extraction", re.compile(
        r"\b(reveal|show|print|output|display|expose|leak|dump)\b.{0,40}\b(api\s*key|secret|password|token|credential|private\s+key)\b",
        re.IGNORECASE | re.DOTALL,
    )),
    # Instruction continuation injection
    ("continuation_injection", re.compile(
        r"\n\s*(new\s+instruction|updated?\s+instruction|additional\s+instruction|system\s+message)\s*:",
        re.IGNORECASE,
    )),
    # Delimited override blocks
    ("delimiter_override", re.compile(
        r"(---+\s*(NEW|OVERRIDE|REVISED|HIDDEN)\s*(INSTRUCTION|PROMPT|CONTEXT)\s*---+)",
        re.IGNORECASE,
    )),
    # Fake tool / function call injection
    ("fake_function_call", re.compile(
        r"<function_calls?>|<tool_call>|\{\s*\"type\"\s*:\s*\"function\"",
        re.IGNORECASE,
    )),
    # ASCII / Unicode obfuscation markers
    ("unicode_obfuscation", re.compile(
        r"[\u200b\u200c\u200d\u2060\ufeff]",  # zero-width spaces / BOM
    )),
]

# Heuristic thresholds
_IMPERATIVE_VERBS = re.compile(
    r"\b(ignore|forget|disregard|stop|start|always|never|must|do not|don't|instead|now)\b",
    re.IGNORECASE,
)
_ROLE_PLAY_WORDS = re.compile(
    r"\b(character|persona|role|mode|assistant|ai|gpt|claude|llm|model|chatbot)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    """Result of a prompt injection scan.

    Attributes:
        is_injection:   True if injection was detected.
        confidence:     0.0–1.0 confidence that this is an injection attempt.
        matched_patterns: Names of patterns that fired.
        heuristic_score: Raw heuristic value (0.0–1.0).
        sanitised_text: Cleaned version of the input (patterns replaced).
        details:        Additional diagnostic information.
    """

    is_injection: bool
    confidence: float
    matched_patterns: list[str] = field(default_factory=list)
    heuristic_score: float = 0.0
    sanitised_text: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class PromptInjectionDetector:
    """Stateless, multi-layer prompt injection detector.

    Parameters:
        pattern_threshold:  Confidence added per matched pattern.
        heuristic_weight:   Weight of heuristic score in final confidence.
        block_threshold:    Confidence ≥ this → ``is_injection=True``.
        placeholder:        Replacement text for sanitised patterns.
    """

    def __init__(
        self,
        pattern_threshold: float = 0.55,
        heuristic_weight: float = 0.3,
        block_threshold: float = 0.5,
        placeholder: str = "[FILTERED]",
    ) -> None:
        self._pattern_threshold = pattern_threshold
        self._heuristic_weight = heuristic_weight
        self._block_threshold = block_threshold
        self._placeholder = placeholder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, text: str, *, source: str = "unknown") -> ScanResult:
        """Scan ``text`` for injection signals.

        Parameters:
            text:   The text to check (user input, tool output, memory chunk, etc.)
            source: Label for logging (e.g. ``"user_input"``, ``"tool_output"``).

        Returns:
            ``ScanResult`` with ``is_injection`` and ``confidence``.
        """
        if not text or not text.strip():
            return ScanResult(
                is_injection=False,
                confidence=0.0,
                sanitised_text=text,
            )

        matched: list[str] = []
        sanitised = text

        # Layer 1 — pattern matching
        for name, pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                matched.append(name)
                sanitised = pattern.sub(self._placeholder, sanitised)

        pattern_confidence = min(len(matched) * self._pattern_threshold, 0.9)

        # Layer 2 — heuristic scoring
        heuristic = self._heuristic_score(text)
        combined_confidence = min(
            pattern_confidence + heuristic * self._heuristic_weight, 1.0
        )
        is_injection = combined_confidence >= self._block_threshold

        if is_injection:
            logger.warning(
                "prompt_injection.detected",
                source=source,
                confidence=round(combined_confidence, 3),
                patterns=matched,
                heuristic=round(heuristic, 3),
            )
        else:
            logger.debug(
                "prompt_injection.clean",
                source=source,
                confidence=round(combined_confidence, 3),
            )

        return ScanResult(
            is_injection=is_injection,
            confidence=round(combined_confidence, 3),
            matched_patterns=matched,
            heuristic_score=round(heuristic, 3),
            sanitised_text=sanitised,
            details={
                "source": source,
                "pattern_confidence": round(pattern_confidence, 3),
                "heuristic_confidence": round(heuristic * self._heuristic_weight, 3),
                "char_count": len(text),
            },
        )

    def sanitise(self, text: str) -> str:
        """Return the input with all detected injection patterns replaced."""
        return self.scan(text).sanitised_text

    def is_safe(self, text: str, *, source: str = "unknown") -> bool:
        """Return True if the text passes injection checks."""
        return not self.scan(text, source=source).is_injection

    # ------------------------------------------------------------------
    # Heuristic scoring
    # ------------------------------------------------------------------

    def _heuristic_score(self, text: str) -> float:
        """Return a 0.0–1.0 score based on statistical signals."""
        score = 0.0
        word_count = max(len(text.split()), 1)

        # Imperative verb density
        imperative_hits = len(_IMPERATIVE_VERBS.findall(text))
        imperative_density = imperative_hits / word_count
        score += min(imperative_density * 3.0, 0.4)

        # Role-play word density
        role_hits = len(_ROLE_PLAY_WORDS.findall(text))
        role_density = role_hits / word_count
        score += min(role_density * 2.0, 0.3)

        # Unusual newline density (injection often uses newlines to inject)
        newline_ratio = text.count("\n") / max(len(text), 1)
        score += min(newline_ratio * 10.0, 0.3)

        # All-caps bursts (shouting instructions)
        caps_words = sum(1 for w in text.split() if len(w) > 2 and w.isupper())
        caps_ratio = caps_words / word_count
        score += min(caps_ratio * 2.0, 0.2)

        return min(score, 1.0)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_DEFAULT_DETECTOR = PromptInjectionDetector()


def scan_input(text: str, *, source: str = "user_input") -> ScanResult:
    """Scan text using the default detector."""
    return _DEFAULT_DETECTOR.scan(text, source=source)


def check_tool_output(output: Any, *, tool_name: str = "unknown") -> ScanResult:
    """Scan a tool's output for injection content before it enters the context.

    Works on strings, dicts (stringified), or any object with ``__str__``.
    """
    if isinstance(output, dict):
        text = str(output)
    elif isinstance(output, str):
        text = output
    else:
        text = str(output)

    return _DEFAULT_DETECTOR.scan(text, source=f"tool_output:{tool_name}")


def sanitise_user_input(text: str) -> str:
    """Sanitise user-provided text before injecting into prompts."""
    # Strip leading/trailing whitespace, normalise newlines
    text = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    # Remove zero-width chars
    text = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)
    # Apply pattern-based sanitisation
    return _DEFAULT_DETECTOR.sanitise(text)
