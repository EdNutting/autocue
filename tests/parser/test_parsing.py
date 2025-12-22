# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Tests for core parsing functions in the script_parser module.
"""

import markdown

from src.autocue.script_parser import (
    ParsedScript,
    SpeakableWord,
    get_speakable_word_list,
    is_silent_punctuation,
    normalize_word,
    parse_script,
    speakable_to_raw_index,
)


class TestNormalizeWord:
    """Tests for the normalize_word function."""

    def test_lowercase_conversion(self) -> None:
        """Words should be converted to lowercase."""
        assert normalize_word("Hello") == "hello"
        assert normalize_word("WORLD") == "world"

    def test_punctuation_stripped(self) -> None:
        """Punctuation should be stripped from words."""
        assert normalize_word("hello,") == "hello"
        assert normalize_word("world!") == "world"
        assert normalize_word("what?") == "what"

    def test_contractions_handled(self) -> None:
        """Contractions should have apostrophe removed."""
        assert normalize_word("don't") == "dont"
        assert normalize_word("it's") == "its"


class TestIsSilentPunctuation:
    """Tests for is_silent_punctuation function."""

    def test_common_punctuation_is_silent(self) -> None:
        """Common punctuation marks should be silent."""
        assert is_silent_punctuation(",") is True
        assert is_silent_punctuation(".") is True
        assert is_silent_punctuation("!") is True
        assert is_silent_punctuation("?") is True
        assert is_silent_punctuation(";") is True
        assert is_silent_punctuation(":") is True

    def test_words_are_not_silent(self) -> None:
        """Normal words should not be marked as silent."""
        assert is_silent_punctuation("hello") is False
        assert is_silent_punctuation("world") is False

    def test_expandable_punctuation_not_silent(self) -> None:
        """Punctuation that expands to words should not be silent."""
        # Note: "&", "/", etc. are not in SILENT_PUNCTUATION
        # The function checks if ALL chars are silent punctuation
        assert is_silent_punctuation("&") is False
        assert is_silent_punctuation("/") is False


class TestParseScript:
    """Tests for the main parse_script function."""

    def test_basic_parsing(self) -> None:
        """Basic script parsing should produce correct structure."""
        script: str = "Hello world"
        parsed: ParsedScript = parse_script(script)

        assert len(parsed.raw_tokens) == 2
        assert len(parsed.speakable_words) == 2
        assert parsed.raw_tokens[0].text == "Hello"
        assert parsed.speakable_words[0].text == "hello"

    def test_punctuation_expansion_in_parsed(self) -> None:
        """Punctuation should be expanded in speakable words."""
        script: str = "A & B"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the expansion words (should include the "&" expansion)
        expansion_words: list[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]

        # Should have at least one expansion word
        assert len(expansion_words) > 0

        # The "&" expansion should have "and" as one of its alternatives
        has_and: bool = any(
            ["and"] in sw.all_expansions
            for sw in expansion_words
        )
        assert has_and, "Expected '&' to have 'and' as an expansion"

    def test_bidirectional_mapping(self) -> None:
        """raw_to_speakable and speakable_to_raw should be inverses."""
        script: str = "Hello world"
        parsed: ParsedScript = parse_script(script)

        for raw_idx, speakable_indices in parsed.raw_to_speakable.items():
            for speakable_idx in speakable_indices:
                assert parsed.speakable_to_raw[speakable_idx] == raw_idx

    def test_expansion_creates_single_speakable_word_with_all_expansions(self) -> None:
        """Expandable tokens create ONE SpeakableWord with all_expansions set."""
        script: str = "A < B"  # "<" expands to ["less", "than"]
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the speakable words from the "<" expansion
        expanded_words: list[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]
        # Now we create ONE position per expandable token
        assert len(expanded_words) == 1

        # The single SpeakableWord should have all_expansions set
        sw: SpeakableWord = expanded_words[0]
        assert sw.all_expansions is not None
        assert len(sw.all_expansions) >= 1
        # First expansion should be ["less", "than"]
        assert sw.all_expansions[0] == ["less", "than"]


class TestSpeakableToRawIndex:
    """Tests for speakable_to_raw_index function."""

    def test_normal_mapping(self) -> None:
        """Normal speakable words should map to their raw tokens."""
        script: str = "Hello world"
        parsed: ParsedScript = parse_script(script)

        assert speakable_to_raw_index(parsed, 0) == 0
        assert speakable_to_raw_index(parsed, 1) == 1

    def test_past_end_returns_length(self) -> None:
        """Index past the end should return len(raw_tokens)."""
        script: str = "Hello world"
        parsed: ParsedScript = parse_script(script)

        result: int = speakable_to_raw_index(parsed, 100)
        assert result == len(parsed.raw_tokens)

    def test_negative_index_returns_zero(self) -> None:
        """Negative index should return 0."""
        script: str = "Hello world"
        parsed: ParsedScript = parse_script(script)

        assert speakable_to_raw_index(parsed, -1) == 0
        assert speakable_to_raw_index(parsed, -100) == 0


class TestGetSpeakableWordList:
    """Tests for get_speakable_word_list function."""

    def test_returns_list_of_strings(self) -> None:
        """Should return a simple list of word strings."""
        script: str = "Hello world"
        parsed: ParsedScript = parse_script(script)

        words: list[str] = get_speakable_word_list(parsed)
        assert isinstance(words, list)
        assert all(isinstance(w, str) for w in words)
        assert words == ["hello", "world"]


class TestEmbeddedPunctuationParsing:
    """Tests for parsing tokens with embedded punctuation like '2^3'."""

    def test_raw_tokens_preserve_html_structure(self) -> None:
        """Raw tokens must preserve original HTML structure for frontend highlighting."""
        script: str = "2^3 equals 8"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw tokens preserve what's in the HTML (important for clickability/highlighting)
        assert parsed.raw_tokens[0].text == "2^3"
        assert parsed.raw_tokens[1].text == "equals"
        assert parsed.raw_tokens[2].text == "8"

        # Verify RawToken.index matches array position
        for i, raw_token in enumerate(parsed.raw_tokens):
            assert raw_token.index == i, (
                f"raw_tokens[{i}].index should be {i}, got {raw_token.index}"
            )

        # But speakable words are split for speech matching
        # 2^3 becomes 3 speakable words: 2, ^, 3
        speakable_from_first_token = [
            parsed.speakable_words[i] for i in parsed.raw_to_speakable[0]
        ]
        assert len(speakable_from_first_token) == 3

        # Verify speakable_to_raw mapping
        # speakable[0,1,2] (from "2^3") should all map to raw_token[0]
        assert parsed.speakable_to_raw[0] == 0  # "2" maps to "2^3"
        assert parsed.speakable_to_raw[1] == 0  # "^" maps to "2^3"
        assert parsed.speakable_to_raw[2] == 0  # "3" maps to "2^3"
        assert parsed.speakable_to_raw[3] == 1  # "equals" maps to "equals"
        assert parsed.speakable_to_raw[4] == 2  # "8" maps to "8"

    def test_exponentiation_simple(self) -> None:
        """'2^3 = 8' should create multiple speakable words from embedded punctuation."""
        script: str = "2^3 = 8"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw tokens should preserve original HTML structure: "2^3", "=", "8"
        assert len(parsed.raw_tokens) == 3
        assert parsed.raw_tokens[0].text == "2^3"
        assert parsed.raw_tokens[1].text == "="
        assert parsed.raw_tokens[2].text == "8"

        # But speakable words should be split: 2, ^, 3, =, 8 (5 speakable words)
        assert len(parsed.speakable_words) == 5

        # The "2^3" raw token should map to 3 speakable words (2, ^, 3)
        assert len(parsed.raw_to_speakable[0]) == 3

        # Check that ^ has expansion
        # Find the speakable words from raw token 0 ("2^3")
        # Should have 3 expansion words: one for "2", one for "^", one for "3"
        speakable_indices = parsed.raw_to_speakable[0]
        expansion_words = [parsed.speakable_words[idx]
                           for idx in speakable_indices if parsed.speakable_words[idx].is_expansion]

        # Should have 2 expansion words: "2" and "^" (both are expansions)
        # "3" is also an expansion, so 3 total
        assert len(expansion_words) == 3

        # Find the caret word - it should have "caret" or "to" as first word
        caret_word: SpeakableWord | None = None
        for sw in expansion_words:
            if sw.all_expansions:
                first_words = [exp[0] for exp in sw.all_expansions]
                if "caret" in first_words or "to" in first_words:
                    caret_word = sw
                    break

        assert caret_word is not None, (
            "Could not find caret expansion. Expansions: "
            f"{[sw.all_expansions for sw in expansion_words]}"
        )
        assert caret_word.is_expansion is True

    def test_exponentiation_variable(self) -> None:
        """'x^n' should create multiple speakable words."""
        script: str = "x^n"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw token preserves original: "x^n"
        assert len(parsed.raw_tokens) == 1
        assert parsed.raw_tokens[0].text == "x^n"

        # Speakable words are split: x, ^, n
        assert len(parsed.speakable_words) == 3

    def test_exponentiation_negative(self) -> None:
        """'2^-3 = 0.125' should create speakable words with minus attached to 3."""
        script: str = "2^-3 = 0.125"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw tokens preserve original: "2^-3", "=", "0.125"
        assert len(parsed.raw_tokens) == 3
        assert parsed.raw_tokens[0].text == "2^-3"
        assert parsed.raw_tokens[1].text == "="
        assert parsed.raw_tokens[2].text == "0.125"

        # Speakable words are split from "2^-3": 2, ^, -3
        # Plus = and 0.125 = 5 speakable words total
        assert len(parsed.speakable_words) == 5

        # The "-3" speakable word should be recognized as a number
        # It should be in the speakable words from raw token 0
        speakable_indices = parsed.raw_to_speakable[0]
        minus_three_word: SpeakableWord | None = None
        for idx in speakable_indices:
            sw = parsed.speakable_words[idx]
            if sw.is_expansion and any("minus" in exp for exp in sw.all_expansions):
                minus_three_word = sw
                break

        assert minus_three_word is not None
        assert minus_three_word.is_expansion is True
        # Should have expansion including "minus three"
        assert any("minus" in exp for exp in minus_three_word.all_expansions)

    def test_embedded_equals_splits(self) -> None:
        """'a=b' should create multiple speakable words."""
        script: str = "a=b"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw token preserves original: "a=b"
        assert len(parsed.raw_tokens) == 1
        assert parsed.raw_tokens[0].text == "a=b"

        # Speakable words are split: a, =, b
        assert len(parsed.speakable_words) == 3

    def test_embedded_ampersand_splits(self) -> None:
        """'A&B' should create multiple speakable words."""
        script: str = "A&B"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw token preserves original: "A&B"
        assert len(parsed.raw_tokens) == 1
        assert parsed.raw_tokens[0].text == "A&B"

        # Speakable words are split: A, &, B
        assert len(parsed.speakable_words) == 3

        # Check that & expands to "and"
        # Find the & expansion in the speakable words from raw token 0
        speakable_indices = parsed.raw_to_speakable[0]
        ampersand_word: SpeakableWord | None = None
        for idx in speakable_indices:
            sw = parsed.speakable_words[idx]
            if sw.is_expansion and ["and"] in sw.all_expansions:
                ampersand_word = sw
                break

        assert ampersand_word is not None
        assert ampersand_word.is_expansion is True
        assert ["and"] in ampersand_word.all_expansions

    def test_forward_slash_preserved_in_units(self) -> None:
        """'100GB/s' should remain as single token (slash preserved)."""
        script: str = "100GB/s"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Should have one raw token: "100GB/s" (slash is preserved)
        assert len(parsed.raw_tokens) == 1
        assert parsed.raw_tokens[0].text == "100GB/s"

        # Should also have one speakable word (slash in units is preserved)
        assert len(parsed.speakable_words) == 1

    def test_complex_calculation(self) -> None:
        """'2^3 + 5 = 13' should create multiple speakable words."""
        script: str = "2^3 + 5 = 13"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw tokens preserve original (when spaces separate): "2^3", "+", "5", "=", "13"
        assert len(parsed.raw_tokens) == 5
        assert parsed.raw_tokens[0].text == "2^3"
        assert parsed.raw_tokens[1].text == "+"
        assert parsed.raw_tokens[2].text == "5"
        assert parsed.raw_tokens[3].text == "="
        assert parsed.raw_tokens[4].text == "13"

        # Speakable words split embedded punctuation: 2, ^, 3, +, 5, =, 13
        assert len(parsed.speakable_words) == 7

    def test_multi_char_operator_embedded(self) -> None:
        """'x<=y' should create multiple speakable words."""
        script: str = "x<=y"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw token preserves original: "x<=y"
        assert len(parsed.raw_tokens) == 1
        assert parsed.raw_tokens[0].text == "x<=y"

        # Speakable words are split: x, <=, y
        assert len(parsed.speakable_words) == 3

        # Check that <= expands correctly
        speakable_indices = parsed.raw_to_speakable[0]
        operator_word: SpeakableWord | None = None
        for idx in speakable_indices:
            sw = parsed.speakable_words[idx]
            if sw.is_expansion and ["less", "than", "or", "equal"] in sw.all_expansions:
                operator_word = sw
                break

        assert operator_word is not None
        assert operator_word.is_expansion is True
        assert ["less", "than", "or", "equal"] in operator_word.all_expansions
