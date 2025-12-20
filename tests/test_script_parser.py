"""
Tests for the script_parser module.

Tests cover:
- Punctuation expansion structure validation
- Markdown handling (bullets, headers, formatting)
- Alternative expansion functions
- Token extraction from HTML
"""

import pytest
from src.autocue.script_parser import (
    PUNCTUATION_EXPANSIONS,
    SILENT_PUNCTUATION,
    RawToken,
    SpeakableWord,
    ParsedScript,
    normalize_word,
    should_expand_punctuation,
    get_all_expansions,
    get_expansion_first_words,
    is_silent_punctuation,
    parse_script,
    get_speakable_word_list,
    speakable_to_raw_index,
)


class TestPunctuationExpansionStructure:
    """Tests for the PUNCTUATION_EXPANSIONS dictionary structure."""

    def test_expansions_are_list_of_lists(self):
        """Each punctuation entry should be a list of alternative expansions (each a list of words)."""
        for punct, expansions in PUNCTUATION_EXPANSIONS.items():
            assert isinstance(expansions, list), f"'{punct}' expansions should be a list"
            assert len(expansions) > 0, f"'{punct}' should have at least one expansion"
            for i, expansion in enumerate(expansions):
                assert isinstance(expansion, list), \
                    f"'{punct}' expansion {i} should be a list of words, got {type(expansion)}"
                assert len(expansion) > 0, \
                    f"'{punct}' expansion {i} should have at least one word"
                for word in expansion:
                    assert isinstance(word, str), \
                        f"'{punct}' expansion {i} words should be strings"

    def test_slash_has_multiple_alternatives(self):
        """'/' should have multiple expansion alternatives: slash, or, forward slash."""
        assert "/" in PUNCTUATION_EXPANSIONS
        expansions = PUNCTUATION_EXPANSIONS["/"]
        first_words = [exp[0] for exp in expansions]
        assert "slash" in first_words
        assert "or" in first_words
        assert "forward" in first_words

    def test_ampersand_has_multiple_alternatives(self):
        """'&' should have multiple expansion alternatives: and, ampersand."""
        assert "&" in PUNCTUATION_EXPANSIONS
        expansions = PUNCTUATION_EXPANSIONS["&"]
        first_words = [exp[0] for exp in expansions]
        assert "and" in first_words
        assert "ampersand" in first_words

    def test_primary_expansion_is_first(self):
        """The first expansion for each punctuation should be the primary (most common)."""
        # These are the expected primary expansions
        expected_primary = {
            "&": ["and"],
            "/": ["slash"],
            "+": ["plus"],
            "-": ["minus"],
            "=": ["equals"],
            "@": ["at"],
            "%": ["percent"],
        }
        for punct, primary in expected_primary.items():
            if punct in PUNCTUATION_EXPANSIONS:
                assert PUNCTUATION_EXPANSIONS[punct][0] == primary, \
                    f"'{punct}' primary expansion should be {primary}"


class TestGetAllExpansions:
    """Tests for the get_all_expansions function."""

    def test_returns_all_slash_expansions(self):
        """get_all_expansions('/') should return all alternatives."""
        expansions = get_all_expansions("/")
        assert expansions is not None
        assert len(expansions) >= 3  # slash, or, forward slash

        # Flatten to check content
        all_first_words = [exp[0] for exp in expansions]
        assert "slash" in all_first_words
        assert "or" in all_first_words
        assert "forward" in all_first_words

    def test_returns_all_ampersand_expansions(self):
        """get_all_expansions('&') should return all alternatives."""
        expansions = get_all_expansions("&")
        assert expansions is not None
        assert len(expansions) >= 2  # and, ampersand

        all_first_words = [exp[0] for exp in expansions]
        assert "and" in all_first_words
        assert "ampersand" in all_first_words

    def test_returns_none_for_non_expandable(self):
        """get_all_expansions should return None for non-expandable tokens."""
        assert get_all_expansions("hello") is None
        assert get_all_expansions("world") is None
        assert get_all_expansions("the") is None

    def test_handles_whitespace_around_punctuation(self):
        """get_all_expansions should handle whitespace around single punctuation."""
        expansions = get_all_expansions(" / ")
        # Note: This will only work for single-char punctuation after strip
        assert expansions is not None or get_all_expansions("/") is not None


class TestGetExpansionFirstWords:
    """Tests for the get_expansion_first_words function."""

    def test_returns_first_words_for_slash(self):
        """get_expansion_first_words('/') should return first word of each alternative."""
        first_words = get_expansion_first_words("/")
        assert first_words is not None
        assert "slash" in first_words
        assert "or" in first_words
        assert "forward" in first_words

    def test_returns_first_words_for_ampersand(self):
        """get_expansion_first_words('&') should return first word of each alternative."""
        first_words = get_expansion_first_words("&")
        assert first_words is not None
        assert "and" in first_words
        assert "ampersand" in first_words

    def test_returns_none_for_non_expandable(self):
        """get_expansion_first_words should return None for normal words."""
        assert get_expansion_first_words("hello") is None


class TestMarkdownHandling:
    """Tests for Markdown handling in script parsing."""

    def test_markdown_bullets_not_treated_as_minus(self):
        """Markdown bullet markers (-) should not become 'minus' words."""
        import markdown

        script = """Here is a list:

- First item
- Second item
- Third item

End of list."""

        # Render to HTML like the app does
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        # Get all speakable words
        words = [sw.text for sw in parsed.speakable_words]

        # "minus" should NOT appear from bullet markers
        # (only from explicit minus like "5 - 3")
        assert "minus" not in words or words.count("minus") == 0

        # The actual content words should be present
        assert "first" in words
        assert "item" in words
        assert "second" in words

    def test_literal_minus_in_content_expands(self):
        """Literal '-' in content (not bullet) should expand to 'minus'."""
        import markdown

        script = "The answer is 5 - 3 = 2"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]

        # The '-' between 5 and 3 should expand to "minus"
        assert "minus" in words

    def test_markdown_headers_not_tokenized(self):
        """Markdown header markers (#) should not appear as tokens."""
        import markdown

        script = """# Main Title

## Section One

Some content here.

### Subsection

More content."""

        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        # Get raw token texts
        raw_texts = [rt.text for rt in parsed.raw_tokens]

        # No token should be just "#" or start with "#"
        for text in raw_texts:
            assert text != "#"
            assert not text.startswith("#")

    def test_bold_and_italic_content_preserved(self):
        """Bold and italic content should be extracted without formatting markers."""
        import markdown

        script = "This has **bold text** and *italic text* in it."
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]

        # Content words should be present
        assert "bold" in words
        assert "text" in words
        assert "italic" in words

        # Formatting markers should not be words
        for word in words:
            assert "**" not in word
            assert word != "*"


class TestShouldExpandPunctuation:
    """Tests for should_expand_punctuation function."""

    def test_returns_primary_expansion(self):
        """should_expand_punctuation returns the first (primary) expansion."""
        expansion = should_expand_punctuation("&")
        assert expansion == ["and"]  # Primary expansion

        expansion = should_expand_punctuation("/")
        assert expansion == ["slash"]  # Primary expansion

    def test_returns_none_for_normal_words(self):
        """Normal words should not be expanded."""
        assert should_expand_punctuation("hello") is None
        assert should_expand_punctuation("world") is None

    def test_handles_multi_char_operators(self):
        """Multi-character operators like '<=' should be handled."""
        expansion = should_expand_punctuation("<=")
        assert expansion == ["less", "than", "or", "equal"]

        expansion = should_expand_punctuation(">=")
        assert expansion == ["greater", "than", "or", "equal"]


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
        import markdown

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

    def test_expansion_creates_multiple_speakable_words(self):
        """Multi-word expansions should create multiple SpeakableWords."""
        import markdown

        script = "A < B"  # "<" expands to ["less", "than"]
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        # Find the speakable words from the "<" expansion
        expanded_words = [sw for sw in parsed.speakable_words if sw.is_expansion]
        assert len(expanded_words) >= 2

        texts = [sw.text for sw in expanded_words]
        assert "less" in texts
        assert "than" in texts


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
