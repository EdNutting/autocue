"""
Tests for core parsing functions in the script_parser module.
"""

import pytest
import markdown
from src.autocue.script_parser import (
    SILENT_PUNCTUATION,
    normalize_word,
    is_silent_punctuation,
    parse_script,
    get_speakable_word_list,
    speakable_to_raw_index,
)


class TestNormalizeWord:
    """Tests for the normalize_word function."""

    def test_lowercase_conversion(self):
        """Words should be converted to lowercase."""
        assert normalize_word("Hello") == "hello"
        assert normalize_word("WORLD") == "world"

    def test_punctuation_stripped(self):
        """Punctuation should be stripped from words."""
        assert normalize_word("hello,") == "hello"
        assert normalize_word("world!") == "world"
        assert normalize_word("what?") == "what"

    def test_contractions_handled(self):
        """Contractions should have apostrophe removed."""
        assert normalize_word("don't") == "dont"
        assert normalize_word("it's") == "its"


class TestIsSilentPunctuation:
    """Tests for is_silent_punctuation function."""

    def test_common_punctuation_is_silent(self):
        """Common punctuation marks should be silent."""
        assert is_silent_punctuation(",") is True
        assert is_silent_punctuation(".") is True
        assert is_silent_punctuation("!") is True
        assert is_silent_punctuation("?") is True
        assert is_silent_punctuation(";") is True
        assert is_silent_punctuation(":") is True

    def test_words_are_not_silent(self):
        """Normal words should not be marked as silent."""
        assert is_silent_punctuation("hello") is False
        assert is_silent_punctuation("world") is False

    def test_expandable_punctuation_not_silent(self):
        """Punctuation that expands to words should not be silent."""
        # Note: "&", "/", etc. are not in SILENT_PUNCTUATION
        # The function checks if ALL chars are silent punctuation
        assert is_silent_punctuation("&") is False
        assert is_silent_punctuation("/") is False


class TestParseScript:
    """Tests for the main parse_script function."""

    def test_basic_parsing(self):
        """Basic script parsing should produce correct structure."""
        script = "Hello world"
        parsed = parse_script(script)

        assert len(parsed.raw_tokens) == 2
        assert len(parsed.speakable_words) == 2
        assert parsed.raw_tokens[0].text == "Hello"
        assert parsed.speakable_words[0].text == "hello"

    def test_punctuation_expansion_in_parsed(self):
        """Punctuation should be expanded in speakable words."""
        script = "A & B"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]
        assert "and" in words

    def test_bidirectional_mapping(self):
        """raw_to_speakable and speakable_to_raw should be inverses."""
        script = "Hello world"
        parsed = parse_script(script)

        for raw_idx, speakable_indices in parsed.raw_to_speakable.items():
            for speakable_idx in speakable_indices:
                assert parsed.speakable_to_raw[speakable_idx] == raw_idx

    def test_expansion_creates_single_speakable_word_with_all_expansions(self):
        """Expandable tokens create ONE SpeakableWord with all_expansions set."""
        script = "A < B"  # "<" expands to ["less", "than"]
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        # Find the speakable words from the "<" expansion
        expanded_words = [sw for sw in parsed.speakable_words if sw.is_expansion]
        # Now we create ONE position per expandable token
        assert len(expanded_words) == 1

        # The single SpeakableWord should have all_expansions set
        sw = expanded_words[0]
        assert sw.all_expansions is not None
        assert len(sw.all_expansions) >= 1
        # First expansion should be ["less", "than"]
        assert sw.all_expansions[0] == ["less", "than"]


class TestSpeakableToRawIndex:
    """Tests for speakable_to_raw_index function."""

    def test_normal_mapping(self):
        """Normal speakable words should map to their raw tokens."""
        script = "Hello world"
        parsed = parse_script(script)

        assert speakable_to_raw_index(parsed, 0) == 0
        assert speakable_to_raw_index(parsed, 1) == 1

    def test_past_end_returns_length(self):
        """Index past the end should return len(raw_tokens)."""
        script = "Hello world"
        parsed = parse_script(script)

        result = speakable_to_raw_index(parsed, 100)
        assert result == len(parsed.raw_tokens)

    def test_negative_index_returns_zero(self):
        """Negative index should return 0."""
        script = "Hello world"
        parsed = parse_script(script)

        assert speakable_to_raw_index(parsed, -1) == 0
        assert speakable_to_raw_index(parsed, -100) == 0


class TestGetSpeakableWordList:
    """Tests for get_speakable_word_list function."""

    def test_returns_list_of_strings(self):
        """Should return a simple list of word strings."""
        script = "Hello world"
        parsed = parse_script(script)

        words = get_speakable_word_list(parsed)
        assert isinstance(words, list)
        assert all(isinstance(w, str) for w in words)
        assert words == ["hello", "world"]
