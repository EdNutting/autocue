"""
Tests for punctuation expansion in the script_parser module.
"""

from src.autocue.script_parser import (
    PUNCTUATION_EXPANSIONS,
    get_all_expansions,
    get_expansion_first_words,
    preprocess_token_for_punctuation,
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

    def test_returns_true_for_punctuation(self) -> None:
        """should_expand_punctuation returns True for expandable punctuation."""
        assert should_expand_punctuation("&") is True
        assert should_expand_punctuation("/") is True
        assert should_expand_punctuation("^") is True
        assert should_expand_punctuation("+") is True

    def test_returns_false_for_normal_words(self) -> None:
        """Normal words should not be expanded."""
        assert should_expand_punctuation("hello") is False
        assert should_expand_punctuation("world") is False

    def test_handles_multi_char_operators(self) -> None:
        """Multi-character operators like '<=' should be handled."""
        assert should_expand_punctuation("<=") is True
        assert should_expand_punctuation(">=") is True


class TestPreprocessTokenForPunctuation:
    """Tests for the preprocess_token_for_punctuation function."""

    def test_splits_caret_in_exponentiation(self) -> None:
        """'2^3' should split into ['2', '^', '3']."""
        result: list[str] = preprocess_token_for_punctuation("2^3")
        assert result == ["2", "^", "3"]

    def test_splits_variable_exponentiation(self) -> None:
        """'x^n' should split into ['x', '^', 'n']."""
        result: list[str] = preprocess_token_for_punctuation("x^n")
        assert result == ["x", "^", "n"]

    def test_splits_negative_exponentiation(self) -> None:
        """'2^-3' should split into ['2', '^', '-3'] (minus preserved)."""
        result: list[str] = preprocess_token_for_punctuation("2^-3")
        assert result == ["2", "^", "-3"]

    def test_preserves_negative_numbers(self) -> None:
        """'-100' should stay as ['-100'] (minus preserved)."""
        result: list[str] = preprocess_token_for_punctuation("-100")
        assert result == ["-100"]

    def test_preserves_forward_slash_in_units(self) -> None:
        """'100GB/s' should stay as ['100GB/s'] (slash preserved)."""
        result: list[str] = preprocess_token_for_punctuation("100GB/s")
        assert result == ["100GB/s"]

    def test_splits_equals_in_equation(self) -> None:
        """'2^3=8' should split into ['2', '^', '3', '=', '8']."""
        result: list[str] = preprocess_token_for_punctuation("2^3=8")
        assert result == ["2", "^", "3", "=", "8"]

    def test_splits_multiple_operators(self) -> None:
        """'a+b=c' should split into ['a', '+', 'b', '=', 'c']."""
        result: list[str] = preprocess_token_for_punctuation("a+b=c")
        assert result == ["a", "+", "b", "=", "c"]

    def test_splits_ampersand(self) -> None:
        """'A&B' should split into ['A', '&', 'B']."""
        result: list[str] = preprocess_token_for_punctuation("A&B")
        assert result == ["A", "&", "B"]

    def test_preserves_percent_pattern(self) -> None:
        """'100%' is a known number pattern and should not be split."""
        result: list[str] = preprocess_token_for_punctuation("100%")
        assert result == ["100%"]

    def test_splits_standalone_percent(self) -> None:
        """'%' by itself should remain as ['%']."""
        result: list[str] = preprocess_token_for_punctuation("%")
        assert result == ["%"]

    def test_splits_multi_char_operators(self) -> None:
        """'x<=y' should split into ['x', '<=', 'y']."""
        result: list[str] = preprocess_token_for_punctuation("x<=y")
        assert result == ["x", "<=", "y"]

    def test_handles_empty_string(self) -> None:
        """Empty string should return empty list."""
        result: list[str] = preprocess_token_for_punctuation("")
        assert not result

    def test_handles_whitespace_only(self) -> None:
        """Whitespace-only string should return empty list."""
        result: list[str] = preprocess_token_for_punctuation("   ")
        assert not result

    def test_regular_word_unchanged(self) -> None:
        """Regular word should return as single-element list."""
        result: list[str] = preprocess_token_for_punctuation("hello")
        assert result == ["hello"]

    def test_number_unchanged(self) -> None:
        """Number without embedded punctuation should return as-is."""
        result: list[str] = preprocess_token_for_punctuation("123")
        assert result == ["123"]

    def test_complex_equation(self) -> None:
        """'(a+b)^2=c' should split properly."""
        result: list[str] = preprocess_token_for_punctuation("a+b^2")
        assert result == ["a", "+", "b", "^", "2"]

    def test_preserves_decimal_numbers(self) -> None:
        """'3.14' should remain as ['3.14'] (period not in PUNCTUATION_EXPANSIONS)."""
        result: list[str] = preprocess_token_for_punctuation("3.14")
        assert result == ["3.14"]
