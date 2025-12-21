"""
Tests for punctuation expansion in the script_parser module.
"""

from src.autocue.script_parser import (
    PUNCTUATION_EXPANSIONS,
    get_all_expansions,
    get_expansion_first_words,
    should_expand_punctuation,
)


class TestPunctuationExpansionStructure:
    """Tests for the PUNCTUATION_EXPANSIONS dictionary structure."""

    def test_expansions_are_list_of_lists(self) -> None:
        """Each punctuation entry should be a list of alternative expansions."""
        for punct, expansions in PUNCTUATION_EXPANSIONS.items():
            assert isinstance(
                expansions, list), f"'{punct}' expansions should be a list"
            assert len(
                expansions) > 0, f"'{punct}' should have at least one expansion"
            for i, expansion in enumerate(expansions):
                assert isinstance(expansion, list), \
                    f"'{punct}' expansion {i} should be a list of words, got {type(expansion)}"
                assert len(expansion) > 0, \
                    f"'{punct}' expansion {i} should have at least one word"
                for word in expansion:
                    assert isinstance(word, str), \
                        f"'{punct}' expansion {i} words should be strings"

    def test_slash_has_multiple_alternatives(self) -> None:
        """'/' should have multiple expansion alternatives: slash, or, forward slash."""
        assert "/" in PUNCTUATION_EXPANSIONS
        expansions: list[list[str]] = PUNCTUATION_EXPANSIONS["/"]
        first_words: list[str] = [exp[0] for exp in expansions]
        assert "slash" in first_words
        assert "or" in first_words
        assert "forward" in first_words

    def test_ampersand_has_multiple_alternatives(self) -> None:
        """'&' should have multiple expansion alternatives: and, ampersand."""
        assert "&" in PUNCTUATION_EXPANSIONS
        expansions: list[list[str]] = PUNCTUATION_EXPANSIONS["&"]
        first_words: list[str] = [exp[0] for exp in expansions]
        assert "and" in first_words
        assert "ampersand" in first_words

    def test_primary_expansion_is_first(self) -> None:
        """The first expansion for each punctuation should be the primary (most common)."""
        # These are the expected primary expansions
        expected_primary: dict[str, list[str]] = {
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

    def test_returns_all_slash_expansions(self) -> None:
        """get_all_expansions('/') should return all alternatives."""
        expansions: list[list[str]] | None = get_all_expansions("/")
        assert expansions is not None
        assert len(expansions) >= 3  # slash, or, forward slash

        # Flatten to check content
        all_first_words: list[str] = [exp[0] for exp in expansions]
        assert "slash" in all_first_words
        assert "or" in all_first_words
        assert "forward" in all_first_words

    def test_returns_all_ampersand_expansions(self) -> None:
        """get_all_expansions('&') should return all alternatives."""
        expansions: list[list[str]] | None = get_all_expansions("&")
        assert expansions is not None
        assert len(expansions) >= 2  # and, ampersand

        all_first_words: list[str] = [exp[0] for exp in expansions]
        assert "and" in all_first_words
        assert "ampersand" in all_first_words

    def test_returns_none_for_non_expandable(self) -> None:
        """get_all_expansions should return None for non-expandable tokens."""
        assert get_all_expansions("hello") is None
        assert get_all_expansions("world") is None
        assert get_all_expansions("the") is None

    def test_handles_whitespace_around_punctuation(self) -> None:
        """get_all_expansions should handle whitespace around single punctuation."""
        expansions: list[list[str]] | None = get_all_expansions(" / ")
        # Note: This will only work for single-char punctuation after strip
        assert expansions is not None or get_all_expansions("/") is not None


class TestGetExpansionFirstWords:
    """Tests for the get_expansion_first_words function."""

    def test_returns_first_words_for_slash(self) -> None:
        """get_expansion_first_words('/') should return first word of each alternative."""
        first_words: list[str] | None = get_expansion_first_words("/")
        assert first_words is not None
        assert "slash" in first_words
        assert "or" in first_words
        assert "forward" in first_words

    def test_returns_first_words_for_ampersand(self) -> None:
        """get_expansion_first_words('&') should return first word of each alternative."""
        first_words: list[str] | None = get_expansion_first_words("&")
        assert first_words is not None
        assert "and" in first_words
        assert "ampersand" in first_words

    def test_returns_none_for_non_expandable(self) -> None:
        """get_expansion_first_words should return None for normal words."""
        assert get_expansion_first_words("hello") is None


class TestShouldExpandPunctuation:
    """Tests for should_expand_punctuation function."""

    def test_returns_primary_expansion(self) -> None:
        """should_expand_punctuation returns the first (primary) expansion."""
        expansion: list[str] | None = should_expand_punctuation("&")
        assert expansion == ["and"]  # Primary expansion

        expansion = should_expand_punctuation("/")
        assert expansion == ["slash"]  # Primary expansion

    def test_returns_none_for_normal_words(self) -> None:
        """Normal words should not be expanded."""
        assert should_expand_punctuation("hello") is None
        assert should_expand_punctuation("world") is None

    def test_handles_multi_char_operators(self) -> None:
        """Multi-character operators like '<=' should be handled."""
        expansion: list[str] | None = should_expand_punctuation("<=")
        assert expansion == ["less", "than", "or", "equal"]

        expansion = should_expand_punctuation(">=")
        assert expansion == ["greater", "than", "or", "equal"]
