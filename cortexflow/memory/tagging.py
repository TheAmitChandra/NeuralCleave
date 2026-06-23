"""Lightweight heuristic tag extraction for long-term memory entries.

No NLP dependency required: combines three signals — explicit #hashtags,
multi-word capitalized phrases (a cheap proper-noun detector), and matches
against a small built-in topic keyword list. This is intentionally simple;
it gives memory entries searchable tags without pulling in spaCy/NLTK.
"""

from __future__ import annotations

import re

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "i", "you", "he", "she",
    "it", "we", "they", "this", "that", "to", "of", "in", "on", "for",
    "and", "or", "but", "with", "as", "at", "by", "from", "be", "have",
    "has", "had", "do", "does", "did", "not", "so", "if", "my", "your",
    "his", "her", "its", "our", "their", "what", "when", "where", "who",
    "how", "why", "can", "will", "would", "should", "could",
})

_TOPIC_KEYWORDS = frozenset({
    "python", "javascript", "typescript", "rust", "golang", "java", "sql",
    "docker", "kubernetes", "react", "vue", "api", "database", "redis",
    "qdrant", "sqlite", "postgres", "telegram", "discord", "slack",
    "email", "voice", "music", "movie", "book", "travel", "food", "health",
    "fitness", "finance", "budget", "work", "meeting", "project",
    "deadline", "birthday", "family", "vacation", "recipe", "weather",
})

_HASHTAG_RE = re.compile(r"#(\w+)")
_STRIP_CHARS = ".,!?;:\"'()[]"


def extract_tags(text: str, max_tags: int = 5) -> list[str]:
    """Extract up to *max_tags* heuristic tags from *text*.

    Priority order: #hashtags, then capitalized phrases, then topic
    keyword matches. Duplicates are removed case-insensitively, keeping
    the first-seen casing.
    """
    if not text:
        return []

    tags: list[str] = []
    seen: set[str] = set()

    def _add(tag: str) -> None:
        key = tag.lower()
        if key and key not in seen:
            seen.add(key)
            tags.append(tag)

    for match in _HASHTAG_RE.finditer(text):
        _add(match.group(1).lower())

    for phrase in _capitalized_phrases(text):
        _add(phrase)

    lowered = text.lower()
    for keyword in sorted(_TOPIC_KEYWORDS):
        if keyword in lowered:
            _add(keyword)

    return tags[:max_tags]


def _capitalized_phrases(text: str) -> list[str]:
    """Find runs of consecutive capitalized, non-stopword tokens.

    A lone capitalized word at the very start of the text is skipped —
    that's almost always just sentence-initial capitalization rather than
    a proper noun.
    """
    words = text.split()
    phrases: list[str] = []
    current: list[str] = []
    current_start = 0

    for idx, raw in enumerate(words):
        word = raw.strip(_STRIP_CHARS)
        is_candidate = bool(word) and word[0].isupper() and word.lower() not in _STOPWORDS
        if is_candidate:
            if not current:
                current_start = idx
            current.append(word)
        else:
            if current:
                _flush_phrase(current, current_start, phrases)
            current = []

    if current:
        _flush_phrase(current, current_start, phrases)

    return phrases


def _flush_phrase(current: list[str], start_idx: int, phrases: list[str]) -> None:
    if len(current) == 1 and start_idx == 0:
        return
    phrases.append(" ".join(current))
