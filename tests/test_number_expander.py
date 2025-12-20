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

import pytest
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


class TestIsNumberToken:
    """Tests for is_number_token detection."""

    def test_pure_integers(self):
        """Pure integers should be detected."""
        assert is_number_token("100") is True
        assert is_number_token("1000") is True
        assert is_number_token("1000000") is True
        assert is_number_token("0") is True
        assert is_number_token("1") is True

    def test_negative_integers(self):
        """Negative integers should be detected."""
        assert is_number_token("-100") is True
        assert is_number_token("-1") is True

    def test_comma_integers(self):
        """Comma-separated integers should be detected."""
        assert is_number_token("1,100") is True
        assert is_number_token("1,000,000") is True
        assert is_number_token("10,000") is True
        assert is_number_token("11,000") is True

    def test_decimals(self):
        """Decimal numbers should be detected."""
        assert is_number_token("3.07") is True
        assert is_number_token("0.3") is True
        assert is_number_token("0.33") is True
        assert is_number_token("0.5") is True
        assert is_number_token("3.14159") is True

    def test_ordinals(self):
        """Ordinal numbers should be detected."""
        assert is_number_token("1st") is True
        assert is_number_token("2nd") is True
        assert is_number_token("3rd") is True
        assert is_number_token("4th") is True
        assert is_number_token("23rd") is True
        assert is_number_token("101st") is True
        assert is_number_token("1ST") is True  # Case insensitive

    def test_mixed_alphanumeric_prefix(self):
        """Mixed alphanumeric with letter prefix should be detected."""
        assert is_number_token("M3") is True
        assert is_number_token("V8") is True
        assert is_number_token("A1") is True
        assert is_number_token("iPhone12") is True

    def test_mixed_alphanumeric_suffix(self):
        """Mixed alphanumeric with letter suffix should be detected."""
        assert is_number_token("4K") is True
        assert is_number_token("100GB") is True
        assert is_number_token("4.05GHz") is True
        assert is_number_token("5m") is True
        assert is_number_token("10s") is True

    def test_regular_words_not_detected(self):
        """Regular words should not be detected as numbers."""
        assert is_number_token("hello") is False
        assert is_number_token("world") is False
        assert is_number_token("the") is False
        assert is_number_token("test") is False

    def test_punctuation_not_detected(self):
        """Punctuation should not be detected as numbers."""
        assert is_number_token("&") is False
        assert is_number_token("/") is False
        assert is_number_token(".") is False
        assert is_number_token(",") is False

    def test_empty_and_whitespace(self):
        """Empty and whitespace should not be detected."""
        assert is_number_token("") is False
        assert is_number_token("   ") is False


class TestExpandInteger:
    """Tests for integer expansion."""

    def test_hundred(self):
        """100 should expand to multiple forms."""
        expansions = expand_integer(100)

        # Should have "one hundred"
        assert ["one", "hundred"] in expansions
        # Should have "a hundred"
        assert ["a", "hundred"] in expansions
        # Should have digit-by-digit
        assert ["one", "zero", "zero"] in expansions

    def test_eleven_hundred(self):
        """1100 should have 'eleven hundred' alternative."""
        expansions = expand_integer(1100)

        # Should have "one thousand one hundred"
        assert any("thousand" in exp for exp in expansions)
        # Should have "eleven hundred"
        assert ["eleven", "hundred"] in expansions
        # Should have digit-by-digit
        assert ["one", "one", "zero", "zero"] in expansions

    def test_twelve_hundred(self):
        """1200 should have 'twelve hundred' alternative."""
        expansions = expand_integer(1200)

        assert ["twelve", "hundred"] in expansions

    def test_thousand(self):
        """1000 should have 'a thousand' alternative."""
        expansions = expand_integer(1000)

        assert ["one", "thousand"] in expansions
        assert ["a", "thousand"] in expansions

    def test_large_number(self):
        """Large numbers should still work."""
        expansions = expand_integer(1000000)

        # Should have "one million"
        assert any("million" in exp for exp in expansions)

    def test_small_numbers(self):
        """Small numbers should work."""
        expansions = expand_integer(1)
        assert ["one"] in expansions

        expansions = expand_integer(10)
        assert ["ten"] in expansions

        expansions = expand_integer(25)
        assert ["twenty", "five"] in expansions

    def test_negative_integer(self):
        """Negative integers should have 'minus' prefix."""
        expansions = expand_integer(-100)

        # Primary should start with minus
        assert expansions[0][0] == "minus"
        assert ["minus", "one", "hundred"] in expansions


class TestExpandDecimal:
    """Tests for decimal expansion."""

    def test_point_zero_seven(self):
        """3.07 should expand with zero/oh variants."""
        expansions = expand_decimal("3.07")

        # Should have "three point zero seven"
        assert ["three", "point", "zero", "seven"] in expansions
        # Should have "three point oh seven"
        assert ["three", "point", "oh", "seven"] in expansions

    def test_point_three(self):
        """0.3 should have 'point three' alternative."""
        expansions = expand_decimal("0.3")

        # Should have "zero point three"
        assert ["zero", "point", "three"] in expansions
        # Should have "point three" (omitting zero)
        assert ["point", "three"] in expansions
        # Should have "oh point three"
        assert ["oh", "point", "three"] in expansions
        # Note: 0.3 is not in COMMON_FRACTIONS (0.3 is 3/10, not a simple fraction)

    def test_half(self):
        """0.5 should expand to 'half' alternatives."""
        expansions = expand_decimal("0.5")

        # Should have fraction forms
        assert ["half"] in expansions or ["one", "half"] in expansions
        # Should also have decimal form
        assert any("point" in exp for exp in expansions)

    def test_quarter(self):
        """0.25 should expand to 'quarter' alternatives."""
        expansions = expand_decimal("0.25")

        assert ["quarter"] in expansions or ["one", "quarter"] in expansions

    def test_third(self):
        """0.33 should expand to 'third' alternatives."""
        expansions = expand_decimal("0.33")

        assert ["third"] in expansions or ["one", "third"] in expansions
        # Should also have "zero point three three"
        assert ["zero", "point", "three", "three"] in expansions

    def test_non_leading_zero_decimal(self):
        """Decimals like 3.14 should work."""
        expansions = expand_decimal("3.14")

        assert ["three", "point", "one", "four"] in expansions

    def test_negative_decimal(self):
        """Negative decimals should have 'minus' prefix."""
        expansions = expand_decimal("-3.14")

        assert expansions[0][0] == "minus"


class TestExpandOrdinal:
    """Tests for ordinal expansion."""

    def test_first(self):
        """1st should expand to 'first'."""
        expansions = expand_ordinal("1st")
        assert ["first"] in expansions

    def test_second(self):
        """2nd should expand to 'second'."""
        expansions = expand_ordinal("2nd")
        assert ["second"] in expansions

    def test_third(self):
        """3rd should expand to 'third'."""
        expansions = expand_ordinal("3rd")
        assert ["third"] in expansions

    def test_fourth(self):
        """4th should expand to 'fourth'."""
        expansions = expand_ordinal("4th")
        assert ["fourth"] in expansions

    def test_twenty_third(self):
        """23rd should expand to 'twenty third'."""
        expansions = expand_ordinal("23rd")
        assert ["twenty", "third"] in expansions

    def test_one_hundred_first(self):
        """101st should expand correctly."""
        expansions = expand_ordinal("101st")
        assert any("first" in exp for exp in expansions)

    def test_case_insensitive(self):
        """Ordinal suffixes should be case insensitive."""
        assert expand_ordinal("1ST") == expand_ordinal("1st")
        assert expand_ordinal("2ND") == expand_ordinal("2nd")
        assert expand_ordinal("3RD") == expand_ordinal("3rd")


class TestExpandMixedAlphanumeric:
    """Tests for mixed alphanumeric expansion."""

    def test_m3(self):
        """M3 should expand to 'm three'."""
        expansions = expand_mixed_alphanumeric("M3")
        assert ["m", "three"] in expansions

    def test_v8(self):
        """V8 should expand to 'v eight'."""
        expansions = expand_mixed_alphanumeric("V8")
        assert ["v", "eight"] in expansions

    def test_4k(self):
        """4K should expand with k and thousand."""
        expansions = expand_mixed_alphanumeric("4K")

        assert ["four", "k"] in expansions
        assert ["four", "thousand"] in expansions

    def test_100gb(self):
        """100GB should expand with multiple forms."""
        expansions = expand_mixed_alphanumeric("100GB")

        # Should have letter-by-letter form
        assert any("g" in exp and "b" in exp for exp in expansions)
        # Should have gigabytes form
        assert any("gigabytes" in exp for exp in expansions)

    def test_5m_metres(self):
        """5m should expand to metres/meters."""
        expansions = expand_mixed_alphanumeric("5m")

        assert ["five", "m"] in expansions
        assert any("metres" in exp or "meters" in exp for exp in expansions)

    def test_10s_seconds(self):
        """10s should expand to seconds."""
        expansions = expand_mixed_alphanumeric("10s")

        assert ["ten", "s"] in expansions
        assert any("seconds" in exp for exp in expansions)

    def test_4_point_05_ghz(self):
        """4.05GHz should handle decimal + suffix."""
        expansions = expand_mixed_alphanumeric("4.05GHz")

        # Should have the number part expanded
        assert any("point" in exp for exp in expansions)
        # Should have gigahertz
        assert any("gigahertz" in exp for exp in expansions)

    def test_multi_letter_prefix(self):
        """Multi-letter prefixes like iPhone12 should work."""
        expansions = expand_mixed_alphanumeric("iPhone12")

        # Should spell out letters
        assert any(exp[0] == "i" for exp in expansions)

    def test_500ms_milliseconds(self):
        """500ms should expand to 'five hundred milliseconds'."""
        expansions = expand_mixed_alphanumeric("500ms")

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

    def test_returns_none_for_non_numbers(self):
        """Regular words should return None."""
        assert get_number_expansions("hello") is None
        assert get_number_expansions("world") is None
        assert get_number_expansions("") is None

    def test_returns_list_for_numbers(self):
        """Numbers should return a list of expansions."""
        result = get_number_expansions("100")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(exp, list) for exp in result)

    def test_primary_expansion_first(self):
        """Primary (most common) expansion should be first."""
        result = get_number_expansions("100")
        # First expansion should be the cardinal form
        assert result[0] == ["one", "hundred"]

    def test_ordinal_detection(self):
        """Ordinals should be properly detected and expanded."""
        result = get_number_expansions("1st")
        assert result is not None
        assert ["first"] in result

    def test_comma_integer_detection(self):
        """Comma-separated integers should be detected."""
        result = get_number_expansions("1,000")
        assert result is not None
        assert ["one", "thousand"] in result

    def test_eleven_thousand_comma(self):
        """'11,000' should expand to 'eleven thousand'."""
        result = get_number_expansions("11,000")
        assert result is not None
        assert ["eleven", "thousand"] in result
        # Should also have digit-by-digit
        assert ["one", "one", "zero", "zero", "zero"] in result

    def test_decimal_detection(self):
        """Decimals should be detected."""
        result = get_number_expansions("3.14")
        assert result is not None
        assert any("point" in exp for exp in result)

    def test_mixed_prefix_detection(self):
        """Mixed prefix tokens should be detected."""
        result = get_number_expansions("M3")
        assert result is not None
        assert ["m", "three"] in result

    def test_mixed_suffix_detection(self):
        """Mixed suffix tokens should be detected."""
        result = get_number_expansions("4K")
        assert result is not None
        assert ["four", "k"] in result


class TestCommonFractions:
    """Tests for common fraction mappings."""

    def test_half_defined(self):
        """0.5 should map to half."""
        assert "0.5" in COMMON_FRACTIONS
        assert ["half"] in COMMON_FRACTIONS["0.5"]

    def test_quarter_defined(self):
        """0.25 should map to quarter."""
        assert "0.25" in COMMON_FRACTIONS
        assert ["quarter"] in COMMON_FRACTIONS["0.25"]

    def test_third_defined(self):
        """0.33 should map to third."""
        assert "0.33" in COMMON_FRACTIONS
        assert ["third"] in COMMON_FRACTIONS["0.33"]

    def test_tenth_defined(self):
        """0.1 should map to tenth."""
        assert "0.1" in COMMON_FRACTIONS
        assert ["tenth"] in COMMON_FRACTIONS["0.1"]


class TestUnitExpansions:
    """Tests for unit expansion definitions."""

    def test_data_units_defined(self):
        """Data units should be defined."""
        assert "gb" in UNIT_EXPANSIONS
        assert "mb" in UNIT_EXPANSIONS
        assert "kb" in UNIT_EXPANSIONS
        assert "tb" in UNIT_EXPANSIONS

    def test_frequency_units_defined(self):
        """Frequency units should be defined."""
        assert "hz" in UNIT_EXPANSIONS
        assert "khz" in UNIT_EXPANSIONS
        assert "mhz" in UNIT_EXPANSIONS
        assert "ghz" in UNIT_EXPANSIONS

    def test_distance_units_defined(self):
        """Distance units should be defined."""
        assert "m" in UNIT_EXPANSIONS
        assert "km" in UNIT_EXPANSIONS
        assert "cm" in UNIT_EXPANSIONS

    def test_time_units_defined(self):
        """Time units should be defined."""
        assert "s" in UNIT_EXPANSIONS
        assert "ms" in UNIT_EXPANSIONS

    def test_unit_has_letter_and_word_forms(self):
        """Units should have both letter-by-letter and word forms."""
        gb_expansions = UNIT_EXPANSIONS["gb"]
        # Should have letter form
        assert ["g", "b"] in gb_expansions
        # Should have word form
        assert ["gigabytes"] in gb_expansions


class TestIntegrationWithParser:
    """Integration tests with script_parser."""

    def test_number_in_script_creates_speakable_words(self):
        """Numbers in script should create speakable words."""
        from src.autocue.script_parser import parse_script
        import markdown

        script = "The answer is 100"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]

        # Should have expanded 100 to "one hundred"
        assert "one" in words
        assert "hundred" in words

    def test_ordinal_in_script(self):
        """Ordinals in script should expand correctly."""
        from src.autocue.script_parser import parse_script
        import markdown

        script = "This is the 1st item"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]

        assert "first" in words

    def test_decimal_in_script(self):
        """Decimals in script should expand correctly."""
        from src.autocue.script_parser import parse_script
        import markdown

        script = "The value is 3.14"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]

        assert "three" in words
        assert "point" in words
        assert "one" in words
        assert "four" in words

    def test_mixed_alphanumeric_in_script(self):
        """Mixed alphanumeric in script should expand correctly."""
        from src.autocue.script_parser import parse_script
        import markdown

        script = "The display is 4K resolution"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]

        assert "four" in words
        # Primary expansion uses letter form
        assert "k" in words

    def test_get_all_expansions_returns_number_alternatives(self):
        """get_all_expansions should return number alternatives."""
        from src.autocue.script_parser import get_all_expansions

        expansions = get_all_expansions("100")
        assert expansions is not None
        assert len(expansions) > 1  # Should have multiple alternatives
        assert ["one", "hundred"] in expansions

    def test_number_creates_expansion_speakable_words(self):
        """Numbers should create SpeakableWords with is_expansion=True."""
        from src.autocue.script_parser import parse_script
        import markdown

        script = "Count to 100"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        # Find the expansion words
        expansion_words = [sw for sw in parsed.speakable_words if sw.is_expansion]
        assert len(expansion_words) >= 2  # "one" and "hundred"

    def test_raw_to_speakable_mapping_correct(self):
        """Raw token should map to all its expanded speakable words."""
        from src.autocue.script_parser import parse_script
        import markdown

        script = "100"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        # Raw token 0 ("100") should map to speakable indices [0, 1] ("one", "hundred")
        assert 0 in parsed.raw_to_speakable
        assert len(parsed.raw_to_speakable[0]) == 2

    def test_500ms_in_script(self):
        """500ms in script should expand to 'five hundred' + unit."""
        from src.autocue.script_parser import parse_script
        import markdown

        script = "The latency is 500ms"
        html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
        parsed = parse_script(script, html)

        words = [sw.text for sw in parsed.speakable_words]

        # Should have expanded 500 to "five hundred"
        assert "five" in words
        assert "hundred" in words
        # Should have the unit (primary expansion is letter-by-letter)
        assert "m" in words
        assert "s" in words


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero(self):
        """Zero should expand correctly."""
        expansions = expand_integer(0)
        assert ["zero"] in expansions

    def test_very_large_number(self):
        """Very large numbers should work."""
        expansions = expand_integer(1000000000)
        assert any("billion" in exp for exp in expansions)

    def test_leading_zeros_decimal(self):
        """Decimals with multiple leading zeros should work."""
        expansions = expand_decimal("0.007")
        assert ["zero", "point", "zero", "zero", "seven"] in expansions

    def test_whitespace_handling(self):
        """Tokens with whitespace should be handled."""
        assert is_number_token("  100  ") is True
        expansions = get_number_expansions("  100  ")
        assert expansions is not None

    def test_single_digit_ordinals(self):
        """Single digit ordinals should all work."""
        for num, suffix in [("1", "st"), ("2", "nd"), ("3", "rd"),
                            ("4", "th"), ("5", "th"), ("6", "th"),
                            ("7", "th"), ("8", "th"), ("9", "th")]:
            token = num + suffix
            result = expand_ordinal(token)
            assert len(result) > 0, f"Failed for {token}"

    def test_teen_ordinals(self):
        """Teen ordinals should work correctly."""
        # 11th, 12th, 13th all use "th"
        assert ["eleventh"] in expand_ordinal("11th")
        assert ["twelfth"] in expand_ordinal("12th")
        assert ["thirteenth"] in expand_ordinal("13th")
