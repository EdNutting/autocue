"""
Tests for the number_expander module.

Tests cover:
- Integer expansion (100, 1000, 1100)
- Decimal expansion (3.07, 0.5, 0.33)
- Ordinal expansion (1st, 2nd, 23rd)
- Mixed alphanumeric (M3, 4K, 100GB)
- Common fractions
- Edge cases
"""

from typing import List, Optional

import pytest
import markdown
from src.autocue.number_expander import (
    is_number_token,
    get_number_expansions,
    expand_integer,
    expand_decimal,
    expand_ordinal,
    expand_mixed_alphanumeric,
    COMMON_FRACTIONS,
    UNIT_EXPANSIONS,
)
from src.autocue.script_parser import parse_script, get_all_expansions, ParsedScript, SpeakableWord


class TestIsNumberToken:
    """Tests for is_number_token detection."""

    def test_pure_integers(self) -> None:
        """Pure integers should be detected."""
        assert is_number_token("100") is True
        assert is_number_token("1000") is True
        assert is_number_token("1000000") is True
        assert is_number_token("0") is True
        assert is_number_token("1") is True

    def test_negative_integers(self) -> None:
        """Negative integers should be detected."""
        assert is_number_token("-100") is True
        assert is_number_token("-1") is True

    def test_comma_integers(self) -> None:
        """Comma-separated integers should be detected."""
        assert is_number_token("1,100") is True
        assert is_number_token("1,000,000") is True
        assert is_number_token("10,000") is True
        assert is_number_token("11,000") is True

    def test_decimals(self) -> None:
        """Decimal numbers should be detected."""
        assert is_number_token("3.07") is True
        assert is_number_token("0.3") is True
        assert is_number_token("0.33") is True
        assert is_number_token("0.5") is True
        assert is_number_token("3.14159") is True

    def test_ordinals(self) -> None:
        """Ordinal numbers should be detected."""
        assert is_number_token("1st") is True
        assert is_number_token("2nd") is True
        assert is_number_token("3rd") is True
        assert is_number_token("4th") is True
        assert is_number_token("23rd") is True
        assert is_number_token("101st") is True
        assert is_number_token("1ST") is True  # Case insensitive

    def test_mixed_alphanumeric_prefix(self) -> None:
        """Mixed alphanumeric with letter prefix should be detected."""
        assert is_number_token("M3") is True
        assert is_number_token("V8") is True
        assert is_number_token("A1") is True
        assert is_number_token("iPhone12") is True

    def test_mixed_alphanumeric_suffix(self) -> None:
        """Mixed alphanumeric with letter suffix should be detected."""
        assert is_number_token("4K") is True
        assert is_number_token("100GB") is True
        assert is_number_token("4.05GHz") is True
        assert is_number_token("5m") is True
        assert is_number_token("10s") is True

    def test_regular_words_not_detected(self) -> None:
        """Regular words should not be detected as numbers."""
        assert is_number_token("hello") is False
        assert is_number_token("world") is False
        assert is_number_token("the") is False
        assert is_number_token("test") is False

    def test_punctuation_not_detected(self) -> None:
        """Punctuation should not be detected as numbers."""
        assert is_number_token("&") is False
        assert is_number_token("/") is False
        assert is_number_token(".") is False
        assert is_number_token(",") is False

    def test_empty_and_whitespace(self) -> None:
        """Empty and whitespace should not be detected."""
        assert is_number_token("") is False
        assert is_number_token("   ") is False


class TestExpandInteger:
    """Tests for integer expansion."""

    def test_hundred(self) -> None:
        """100 should expand to multiple forms."""
        expansions: List[List[str]] = expand_integer(100)

        # Should have "one hundred"
        assert ["one", "hundred"] in expansions
        # Should have "a hundred"
        assert ["a", "hundred"] in expansions
        # Should have digit-by-digit
        assert ["one", "zero", "zero"] in expansions

    def test_eleven_hundred(self) -> None:
        """1100 should have 'eleven hundred' alternative."""
        expansions: List[List[str]] = expand_integer(1100)

        # Should have "one thousand one hundred"
        assert any("thousand" in exp for exp in expansions)
        # Should have "eleven hundred"
        assert ["eleven", "hundred"] in expansions
        # Should have digit-by-digit
        assert ["one", "one", "zero", "zero"] in expansions

    def test_twelve_hundred(self) -> None:
        """1200 should have 'twelve hundred' alternative."""
        expansions: List[List[str]] = expand_integer(1200)

        assert ["twelve", "hundred"] in expansions

    def test_thousand(self) -> None:
        """1000 should have 'a thousand' alternative."""
        expansions: List[List[str]] = expand_integer(1000)

        assert ["one", "thousand"] in expansions
        assert ["a", "thousand"] in expansions

    def test_large_number(self) -> None:
        """Large numbers should still work."""
        expansions: List[List[str]] = expand_integer(1000000)

        # Should have "one million"
        assert any("million" in exp for exp in expansions)

    def test_small_numbers(self) -> None:
        """Small numbers should work."""
        expansions: List[List[str]] = expand_integer(1)
        assert ["one"] in expansions

        expansions = expand_integer(10)
        assert ["ten"] in expansions

        expansions = expand_integer(25)
        assert ["twenty", "five"] in expansions

    def test_negative_integer(self) -> None:
        """Negative integers should have 'minus' prefix."""
        expansions: List[List[str]] = expand_integer(-100)

        # Primary should start with minus
        assert expansions[0][0] == "minus"
        assert ["minus", "one", "hundred"] in expansions


class TestExpandDecimal:
    """Tests for decimal expansion."""

    def test_point_zero_seven(self) -> None:
        """3.07 should expand with zero/oh variants."""
        expansions: List[List[str]] = expand_decimal("3.07")

        # Should have "three point zero seven"
        assert ["three", "point", "zero", "seven"] in expansions
        # Should have "three point oh seven"
        assert ["three", "point", "oh", "seven"] in expansions

    def test_point_three(self) -> None:
        """0.3 should have 'point three' alternative."""
        expansions: List[List[str]] = expand_decimal("0.3")

        # Should have "zero point three"
        assert ["zero", "point", "three"] in expansions
        # Should have "point three" (omitting zero)
        assert ["point", "three"] in expansions
        # Should have "oh point three"
        assert ["oh", "point", "three"] in expansions
        # Note: 0.3 is not in COMMON_FRACTIONS (0.3 is 3/10, not a simple fraction)

    def test_half(self) -> None:
        """0.5 should expand to 'half' alternatives."""
        expansions: List[List[str]] = expand_decimal("0.5")

        # Should have fraction forms
        assert ["half"] in expansions or ["one", "half"] in expansions
        # Should also have decimal form
        assert any("point" in exp for exp in expansions)

    def test_quarter(self) -> None:
        """0.25 should expand to 'quarter' alternatives."""
        expansions: List[List[str]] = expand_decimal("0.25")

        assert ["quarter"] in expansions or ["one", "quarter"] in expansions

    def test_third(self) -> None:
        """0.33 should expand to 'third' alternatives."""
        expansions: List[List[str]] = expand_decimal("0.33")

        assert ["third"] in expansions or ["one", "third"] in expansions
        # Should also have "zero point three three"
        assert ["zero", "point", "three", "three"] in expansions

    def test_non_leading_zero_decimal(self) -> None:
        """Decimals like 3.14 should work."""
        expansions: List[List[str]] = expand_decimal("3.14")

        assert ["three", "point", "one", "four"] in expansions

    def test_negative_decimal(self) -> None:
        """Negative decimals should have 'minus' prefix."""
        expansions: List[List[str]] = expand_decimal("-3.14")

        assert expansions[0][0] == "minus"


class TestExpandOrdinal:
    """Tests for ordinal expansion."""

    def test_first(self) -> None:
        """1st should expand to 'first'."""
        expansions: List[List[str]] = expand_ordinal("1st")
        assert ["first"] in expansions

    def test_second(self) -> None:
        """2nd should expand to 'second'."""
        expansions: List[List[str]] = expand_ordinal("2nd")
        assert ["second"] in expansions

    def test_third(self) -> None:
        """3rd should expand to 'third'."""
        expansions: List[List[str]] = expand_ordinal("3rd")
        assert ["third"] in expansions

    def test_fourth(self) -> None:
        """4th should expand to 'fourth'."""
        expansions: List[List[str]] = expand_ordinal("4th")
        assert ["fourth"] in expansions

    def test_twenty_third(self) -> None:
        """23rd should expand to 'twenty third'."""
        expansions: List[List[str]] = expand_ordinal("23rd")
        assert ["twenty", "third"] in expansions

    def test_one_hundred_first(self) -> None:
        """101st should expand correctly."""
        expansions: List[List[str]] = expand_ordinal("101st")
        assert any("first" in exp for exp in expansions)

    def test_case_insensitive(self) -> None:
        """Ordinal suffixes should be case insensitive."""
        assert expand_ordinal("1ST") == expand_ordinal("1st")
        assert expand_ordinal("2ND") == expand_ordinal("2nd")
        assert expand_ordinal("3RD") == expand_ordinal("3rd")


class TestExpandMixedAlphanumeric:
    """Tests for mixed alphanumeric expansion."""

    def test_m3(self) -> None:
        """M3 should expand to 'm three'."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("M3")
        assert ["m", "three"] in expansions

    def test_v8(self) -> None:
        """V8 should expand to 'v eight'."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("V8")
        assert ["v", "eight"] in expansions

    def test_4k(self) -> None:
        """4K should expand with k and thousand."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("4K")

        assert ["four", "k"] in expansions
        assert ["four", "thousand"] in expansions

    def test_100gb(self) -> None:
        """100GB should expand with multiple forms."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("100GB")

        # Should have letter-by-letter form
        assert any("g" in exp and "b" in exp for exp in expansions)
        # Should have gigabytes form
        assert any("gigabytes" in exp for exp in expansions)

    def test_5m_metres(self) -> None:
        """5m should expand to metres/meters."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("5m")

        assert ["five", "m"] in expansions
        assert any("metres" in exp or "meters" in exp for exp in expansions)

    def test_10s_seconds(self) -> None:
        """10s should expand to seconds."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("10s")

        assert ["ten", "s"] in expansions
        assert any("seconds" in exp for exp in expansions)

    def test_4_point_05_ghz(self) -> None:
        """4.05GHz should handle decimal + suffix."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("4.05GHz")

        # Should have the number part expanded
        assert any("point" in exp for exp in expansions)
        # Should have gigahertz
        assert any("gigahertz" in exp for exp in expansions)

    def test_multi_letter_prefix(self) -> None:
        """Multi-letter prefixes like iPhone12 should work."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("iPhone12")

        # Long prefixes (>2 chars) are kept as words, not spelled out
        assert any(exp[0] == "iphone" for exp in expansions)
        assert any("twelve" in exp for exp in expansions)

    def test_500ms_milliseconds(self) -> None:
        """500ms should expand to 'five hundred milliseconds'."""
        expansions: List[List[str]] = expand_mixed_alphanumeric("500ms")

        # Should have letter-by-letter form with number expanded
        assert any(
            "five" in exp and "hundred" in exp and "m" in exp and "s" in exp
            for exp in expansions
        )
        # Should have milliseconds form
        assert any("milliseconds" in exp for exp in expansions)
        # The full expansion should include "five hundred milliseconds"
        assert any(
            exp == ["five", "hundred", "milliseconds"] or
            exp == ["five", "hundred", "millisecond"]
            for exp in expansions
        )


class TestGetNumberExpansions:
    """Tests for the main get_number_expansions entry point."""

    def test_returns_none_for_non_numbers(self) -> None:
        """Regular words should return None."""
        assert get_number_expansions("hello") is None
        assert get_number_expansions("world") is None
        assert get_number_expansions("") is None

    def test_returns_list_for_numbers(self) -> None:
        """Numbers should return a list of expansions."""
        result: Optional[List[List[str]]] = get_number_expansions("100")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(exp, list) for exp in result)

    def test_primary_expansion_first(self) -> None:
        """Primary (most common) expansion should be first."""
        result: Optional[List[List[str]]] = get_number_expansions("100")
        # First expansion should be the cardinal form
        assert result is not None, "100 should have expansions"
        assert result[0] == ["one", "hundred"]

    def test_ordinal_detection(self) -> None:
        """Ordinals should be properly detected and expanded."""
        result: Optional[List[List[str]]] = get_number_expansions("1st")
        assert result is not None
        assert ["first"] in result

    def test_comma_integer_detection(self) -> None:
        """Comma-separated integers should be detected."""
        result: Optional[List[List[str]]] = get_number_expansions("1,000")
        assert result is not None
        assert ["one", "thousand"] in result

    def test_eleven_thousand_comma(self) -> None:
        """'11,000' should expand to 'eleven thousand'."""
        result: Optional[List[List[str]]] = get_number_expansions("11,000")
        assert result is not None
        assert ["eleven", "thousand"] in result
        # Should also have digit-by-digit
        assert ["one", "one", "zero", "zero", "zero"] in result

    def test_decimal_detection(self) -> None:
        """Decimals should be detected."""
        result: Optional[List[List[str]]] = get_number_expansions("3.14")
        assert result is not None
        assert any("point" in exp for exp in result)

    def test_mixed_prefix_detection(self) -> None:
        """Mixed prefix tokens should be detected."""
        result: Optional[List[List[str]]] = get_number_expansions("M3")
        assert result is not None
        assert ["m", "three"] in result

    def test_mixed_suffix_detection(self) -> None:
        """Mixed suffix tokens should be detected."""
        result: Optional[List[List[str]]] = get_number_expansions("4K")
        assert result is not None
        assert ["four", "k"] in result


class TestCommonFractions:
    """Tests for common fraction mappings."""

    def test_half_defined(self) -> None:
        """0.5 should map to half."""
        assert "0.5" in COMMON_FRACTIONS
        assert ["half"] in COMMON_FRACTIONS["0.5"]

    def test_quarter_defined(self) -> None:
        """0.25 should map to quarter."""
        assert "0.25" in COMMON_FRACTIONS
        assert ["quarter"] in COMMON_FRACTIONS["0.25"]

    def test_third_defined(self) -> None:
        """0.33 should map to third."""
        assert "0.33" in COMMON_FRACTIONS
        assert ["third"] in COMMON_FRACTIONS["0.33"]

    def test_tenth_defined(self) -> None:
        """0.1 should map to tenth."""
        assert "0.1" in COMMON_FRACTIONS
        assert ["tenth"] in COMMON_FRACTIONS["0.1"]


class TestUnitExpansions:
    """Tests for unit expansion definitions."""

    def test_data_units_defined(self) -> None:
        """Data units should be defined."""
        assert "gb" in UNIT_EXPANSIONS
        assert "mb" in UNIT_EXPANSIONS
        assert "kb" in UNIT_EXPANSIONS
        assert "tb" in UNIT_EXPANSIONS

    def test_frequency_units_defined(self) -> None:
        """Frequency units should be defined."""
        assert "hz" in UNIT_EXPANSIONS
        assert "khz" in UNIT_EXPANSIONS
        assert "mhz" in UNIT_EXPANSIONS
        assert "ghz" in UNIT_EXPANSIONS

    def test_distance_units_defined(self) -> None:
        """Distance units should be defined."""
        assert "m" in UNIT_EXPANSIONS
        assert "km" in UNIT_EXPANSIONS
        assert "cm" in UNIT_EXPANSIONS

    def test_time_units_defined(self) -> None:
        """Time units should be defined."""
        assert "s" in UNIT_EXPANSIONS
        assert "ms" in UNIT_EXPANSIONS

    def test_unit_has_letter_and_word_forms(self) -> None:
        """Units should have both letter-by-letter and word forms."""
        gb_expansions: List[List[str]] = UNIT_EXPANSIONS["gb"]
        # Should have letter form
        assert ["g", "b"] in gb_expansions
        # Should have word form
        assert ["gigabytes"] in gb_expansions


class TestIntegrationWithParser:
    """Integration tests with script_parser."""

    def test_number_in_script_creates_speakable_words(self) -> None:
        """Numbers in script should create ONE speakable word with all expansions."""
        script: str = "The answer is 100"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the expansion word for "100"
        expansion_words: List[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]
        # ONE speakable word per expandable token
        assert len(expansion_words) == 1

        # The speakable word should have all_expansions containing "one hundred"
        sw: SpeakableWord = expansion_words[0]
        assert sw.all_expansions is not None
        assert ["one", "hundred"] in sw.all_expansions

    def test_ordinal_in_script(self) -> None:
        """Ordinals in script should expand correctly."""
        script: str = "This is the 1st item"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        words: List[str] = [sw.text for sw in parsed.speakable_words]

        assert "first" in words

    def test_decimal_in_script(self) -> None:
        """Decimals in script should create ONE speakable word with all expansions."""
        script: str = "The value is 3.14"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the expansion word for "3.14"
        expansion_words: List[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]
        # ONE speakable word per expandable token
        assert len(expansion_words) == 1

        # The speakable word should have all_expansions containing "three point one four"
        sw: SpeakableWord = expansion_words[0]
        assert sw.all_expansions is not None
        assert ["three", "point", "one", "four"] in sw.all_expansions

    def test_mixed_alphanumeric_in_script(self) -> None:
        """Mixed alphanumeric in script should create ONE speakable word."""
        script: str = "The display is 4K resolution"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the expansion word for "4K"
        expansion_words: List[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]
        # ONE speakable word per expandable token
        assert len(expansion_words) == 1

        # The speakable word should have all_expansions containing "four k"
        sw: SpeakableWord = expansion_words[0]
        assert sw.all_expansions is not None
        assert ["four", "k"] in sw.all_expansions

    def test_get_all_expansions_returns_number_alternatives(self) -> None:
        """get_all_expansions should return number alternatives."""
        expansions: Optional[List[List[str]]] = get_all_expansions("100")
        assert expansions is not None
        assert len(expansions) > 1  # Should have multiple alternatives
        assert ["one", "hundred"] in expansions

    def test_number_creates_expansion_speakable_words(self) -> None:
        """Numbers should create ONE SpeakableWord with is_expansion=True."""
        script: str = "Count to 100"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the expansion words
        expansion_words: List[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]
        # ONE speakable word per expandable token
        assert len(expansion_words) == 1

        # The speakable word should have all_expansions with multiple alternatives
        sw: SpeakableWord = expansion_words[0]
        assert sw.all_expansions is not None
        assert len(sw.all_expansions) >= 2  # Multiple ways to say 100

    def test_raw_to_speakable_mapping_correct(self) -> None:
        """Raw token should map to ONE speakable word with all expansions."""
        script: str = "100"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Raw token 0 ("100") should map to speakable index [0] (single position)
        assert 0 in parsed.raw_to_speakable
        assert len(parsed.raw_to_speakable[0]) == 1

        # The speakable word should have all_expansions containing "one hundred"
        sw: SpeakableWord = parsed.speakable_words[0]
        assert sw.all_expansions is not None
        assert ["one", "hundred"] in sw.all_expansions

    def test_500ms_in_script(self) -> None:
        """500ms in script should create ONE speakable word with all expansions."""
        script: str = "The latency is 500ms"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the expansion word for "500ms"
        expansion_words: List[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]
        # ONE speakable word per expandable token
        assert len(expansion_words) == 1

        # The speakable word should have all_expansions containing "five hundred" + unit
        sw: SpeakableWord = expansion_words[0]
        assert sw.all_expansions is not None
        # Should have "five hundred milliseconds" or similar
        has_five_hundred: bool = any(
            exp[:2] == ["five", "hundred"] for exp in sw.all_expansions
        )
        assert has_five_hundred


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero(self) -> None:
        """Zero should expand correctly."""
        expansions: List[List[str]] = expand_integer(0)
        assert ["zero"] in expansions

    def test_very_large_number(self) -> None:
        """Very large numbers should work."""
        expansions: List[List[str]] = expand_integer(1000000000)
        assert any("billion" in exp for exp in expansions)

    def test_leading_zeros_decimal(self) -> None:
        """Decimals with multiple leading zeros should work."""
        expansions: List[List[str]] = expand_decimal("0.007")
        assert ["zero", "point", "zero", "zero", "seven"] in expansions

    def test_whitespace_handling(self) -> None:
        """Tokens with whitespace should be handled."""
        assert is_number_token("  100  ") is True
        expansions: Optional[List[List[str]]
                             ] = get_number_expansions("  100  ")
        assert expansions is not None

    def test_single_digit_ordinals(self) -> None:
        """Single digit ordinals should all work."""
        for num, suffix in [("1", "st"), ("2", "nd"), ("3", "rd"),
                            ("4", "th"), ("5", "th"), ("6", "th"),
                            ("7", "th"), ("8", "th"), ("9", "th")]:
            token: str = num + suffix
            result: List[List[str]] = expand_ordinal(token)
            assert len(result) > 0, f"Failed for {token}"

    def test_teen_ordinals(self) -> None:
        """Teen ordinals should work correctly."""
        # 11th, 12th, 13th all use "th"
        assert ["eleventh"] in expand_ordinal("11th")
        assert ["twelfth"] in expand_ordinal("12th")
        assert ["thirteenth"] in expand_ordinal("13th")


class TestRateUnits:
    """Tests for rate unit expansions (100GB/s, 1000MB/s, etc.)."""

    def test_rate_unit_is_number_token(self) -> None:
        """Rate units should be recognized as number tokens."""
        assert is_number_token("100GB/s") is True
        assert is_number_token("1000MB/s") is True

    def test_rate_unit_expansion(self) -> None:
        """Rate units should expand correctly."""
        expansions: Optional[List[List[str]]
                             ] = get_number_expansions("100GB/s")
        assert expansions is not None
        # Should have expansion with "per"
        has_per: bool = any("per" in exp for exp in expansions)
        assert has_per, "Rate unit should have 'per' in expansion"

    def test_rate_unit_with_full_words(self) -> None:
        """Rate units should have expansions with full unit words."""
        expansions: Optional[List[List[str]]
                             ] = get_number_expansions("100GB/s")
        assert expansions is not None
        # Should have one with "gigabytes per second" style
        has_full: bool = any(
            "gigabytes" in exp and "second" in exp
            for exp in expansions
        )
        assert has_full, "Should have full word expansion"

    def test_rate_unit_in_script(self) -> None:
        """Rate units in script should create expansion speakable words."""
        script: str = "Memory bandwidth might be 100GB/s"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Find the expansion word for "100GB/s"
        expansion_words: List[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]
        assert len(expansion_words) == 1

        sw: SpeakableWord = expansion_words[0]
        assert sw.all_expansions is not None
        # Check that "per" is in at least one expansion
        has_per: bool = any("per" in exp for exp in sw.all_expansions)
        assert has_per
