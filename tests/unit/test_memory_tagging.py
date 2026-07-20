"""Unit tests for NeuralCleave.memory.tagging — heuristic extract_tags()."""

from __future__ import annotations

from neuralcleave.memory.tagging import extract_tags

# ---------------------------------------------------------------------------
# Basic cases
# ---------------------------------------------------------------------------


def test_empty_text_returns_no_tags():
    assert extract_tags("") == []


def test_plain_lowercase_sentence_no_hits():
    assert extract_tags("just a regular sentence with nothing special") == []


# ---------------------------------------------------------------------------
# Hashtags
# ---------------------------------------------------------------------------


def test_hashtags_extracted_lowercased():
    tags = extract_tags("Remember to read #Python and #Docker")
    assert "python" in tags
    assert "docker" in tags


def test_hashtags_respect_max_tags():
    tags = extract_tags("#a #b #c #d #e #f", max_tags=3)
    assert tags == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Capitalized phrases (proper-noun heuristic)
# ---------------------------------------------------------------------------


def test_multiword_capitalized_phrase_kept():
    tags = extract_tags("Meeting with John Smith about Project Phoenix tomorrow.")
    assert "John Smith" in tags
    assert "Project Phoenix" in tags


def test_sentence_initial_word_not_treated_as_tag():
    tags = extract_tags("Remember to call mom tonight.")
    assert "Remember" not in tags


def test_single_capitalized_word_mid_sentence_is_kept():
    tags = extract_tags("I love using Redis for caching.")
    assert "Redis" in tags


# ---------------------------------------------------------------------------
# Topic keywords
# ---------------------------------------------------------------------------


def test_topic_keyword_matched_case_insensitively():
    tags = extract_tags("i need to update my budget spreadsheet this weekend")
    assert "budget" in tags


def test_topic_keyword_substring_match():
    tags = extract_tags("set up a new docker container for the app")
    assert "docker" in tags


# ---------------------------------------------------------------------------
# Dedup and ordering
# ---------------------------------------------------------------------------


def test_dedup_case_insensitive_keeps_first_seen_casing():
    tags = extract_tags("#Python is great, Python is fun")
    python_tags = [t for t in tags if t.lower() == "python"]
    assert len(python_tags) == 1
    assert python_tags[0] == "python"  # hashtag (lowercased) wins, seen first


def test_max_tags_caps_total_output():
    text = "#a #b #c John Smith Project Phoenix docker redis sql"
    tags = extract_tags(text, max_tags=2)
    assert len(tags) == 2
