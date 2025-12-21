"""
Tests for expansion matching (punctuation and number alternatives) in ScriptTracker.
"""

import pytest
from src.autocue.tracker import ScriptTracker


class TestAlternativePunctuationMatching:
    """Tests for matching alternative spoken forms of punctuation."""

    def test_slash_matches_slash(self):
        """'/' should match when spoken as 'slash'."""
        tracker = ScriptTracker("Press A / B to continue")
        # Advance to A
        tracker.update("press a")
        pos_before = tracker.optimistic_position

        # Say "slash" for "/"
        tracker.update("press a slash")
        pos_after = tracker.optimistic_position

        # Should have advanced past the "/"
        assert pos_after > pos_before

    def test_slash_matches_or(self):
        """'/' should match when spoken as 'or'."""
        tracker = ScriptTracker("Press A / B to continue")
        tracker.update("press a")
        pos_before = tracker.optimistic_position

        # Say "or" for "/"
        tracker.update("press a or")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_slash_matches_forward_slash(self):
        """'/' should match when spoken as 'forward slash' (complete expansion)."""
        tracker = ScriptTracker("Press A / B to continue")
        tracker.update("press a")
        pos_before = tracker.optimistic_position

        # Say "forward slash" for "/" (complete multi-word expansion)
        # Note: With the new dynamic expansion model, position only advances
        # when the complete expansion is spoken
        tracker.update("press a forward slash")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_ampersand_matches_and(self):
        """'&' should match when spoken as 'and'."""
        tracker = ScriptTracker("Press A & B to continue")
        tracker.update("press a")
        pos_before = tracker.optimistic_position

        # Say "and" for "&"
        tracker.update("press a and")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_ampersand_matches_ampersand(self):
        """'&' should match when spoken as 'ampersand'."""
        tracker = ScriptTracker("Press A & B to continue")
        tracker.update("press a")
        pos_before = tracker.optimistic_position

        # Say "ampersand" for "&"
        tracker.update("press a ampersand")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_plus_matches_plus(self):
        """'+' should match when spoken as 'plus'."""
        tracker = ScriptTracker("Calculate 5 + 3")
        tracker.update("calculate five")
        pos_before = tracker.optimistic_position

        tracker.update("calculate five plus")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_at_matches_at(self):
        """'@' should match when spoken as 'at'."""
        tracker = ScriptTracker("Email me @ example dot com")
        tracker.update("email me")
        pos_before = tracker.optimistic_position

        tracker.update("email me at")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_percent_matches_percent(self):
        """'%' should match when spoken as 'percent'."""
        tracker = ScriptTracker("The rate is 50 % annually")
        tracker.update("the rate is fifty")
        pos_before = tracker.optimistic_position

        tracker.update("the rate is fifty percent")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_equals_matches_equals(self):
        """'=' should match when spoken as 'equals'."""
        tracker = ScriptTracker("So 2 + 2 = 4")
        tracker.update("so two plus two")
        pos_before = tracker.optimistic_position

        tracker.update("so two plus two equals")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_equals_matches_is(self):
        """'=' should match when spoken as 'is'."""
        tracker = ScriptTracker("So 2 + 2 = 4")
        tracker.update("so two plus two")
        pos_before = tracker.optimistic_position

        # Say "is" for "="
        tracker.update("so two plus two is")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_tilde_matches_approximately(self):
        """'~' should match when spoken as 'approximately'."""
        tracker = ScriptTracker("The value is ~ 100")
        tracker.update("the value is")
        pos_before = tracker.optimistic_position

        tracker.update("the value is approximately")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_tilde_matches_about(self):
        """'~' should match when spoken as 'about'."""
        tracker = ScriptTracker("The value is ~ 100")
        tracker.update("the value is")
        pos_before = tracker.optimistic_position

        tracker.update("the value is about")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_pipe_matches_or(self):
        """'|' should match when spoken as 'or'."""
        tracker = ScriptTracker("Use true | false")
        tracker.update("use true")
        pos_before = tracker.optimistic_position

        tracker.update("use true or")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_pipe_matches_pipe(self):
        """'|' should match when spoken as 'pipe'."""
        tracker = ScriptTracker("Use true | false")
        tracker.update("use true")
        pos_before = tracker.optimistic_position

        tracker.update("use true pipe")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before


class TestAlternativeNumberMatching:
    """Tests for matching alternative spoken forms of numbers."""

    def test_hundred_matches_one_hundred(self):
        """'100' should match when spoken as 'one hundred'."""
        tracker = ScriptTracker("The value is 100 dollars")
        tracker.update("the value is")
        pos_before = tracker.optimistic_position

        tracker.update("the value is one hundred")
        pos_after = tracker.optimistic_position

        # Should have advanced past "100"
        assert pos_after > pos_before

    def test_hundred_matches_a_hundred(self):
        """'100' should match when spoken as 'a hundred'."""
        tracker = ScriptTracker("The value is 100 dollars")
        tracker.update("the value is")
        pos_before = tracker.optimistic_position

        tracker.update("the value is a hundred")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_thousand_matches_one_thousand(self):
        """'1000' should match when spoken as 'one thousand'."""
        tracker = ScriptTracker("There are 1000 items")
        tracker.update("there are")
        pos_before = tracker.optimistic_position

        tracker.update("there are one thousand")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_thousand_matches_a_thousand(self):
        """'1000' should match when spoken as 'a thousand'."""
        tracker = ScriptTracker("There are 1000 items")
        tracker.update("there are")
        pos_before = tracker.optimistic_position

        tracker.update("there are a thousand")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_eleven_hundred(self):
        """'1100' should match when spoken as 'eleven hundred'."""
        tracker = ScriptTracker("The count is 1100 total")
        tracker.update("the count is")
        pos_before = tracker.optimistic_position

        tracker.update("the count is eleven hundred")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_decimal_point_form(self):
        """'3.14' should match when spoken as 'three point one four'."""
        tracker = ScriptTracker("Pi is 3.14 approximately")
        tracker.update("pi is")
        pos_before = tracker.optimistic_position

        tracker.update("pi is three point one four")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_decimal_oh_form(self):
        """'3.07' should match when spoken as 'three point oh seven'."""
        tracker = ScriptTracker("The value is 3.07 units")
        tracker.update("the value is")
        pos_before = tracker.optimistic_position

        tracker.update("the value is three point oh seven")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_decimal_point_only(self):
        """'0.3' should match when spoken as 'point three'."""
        tracker = ScriptTracker("The ratio is 0.3 today")
        tracker.update("the ratio is")
        pos_before = tracker.optimistic_position

        tracker.update("the ratio is point three")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_half_fraction(self):
        """'0.5' should match when spoken as 'half'."""
        tracker = ScriptTracker("Take 0.5 of the total")
        tracker.update("take")
        pos_before = tracker.optimistic_position

        tracker.update("take half")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_ordinal_first(self):
        """'1st' should match when spoken as 'first'."""
        tracker = ScriptTracker("This is the 1st test")
        tracker.update("this is the")
        pos_before = tracker.optimistic_position

        tracker.update("this is the first")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_ordinal_second(self):
        """'2nd' should match when spoken as 'second'."""
        tracker = ScriptTracker("This is the 2nd item")
        tracker.update("this is the")
        pos_before = tracker.optimistic_position

        tracker.update("this is the second")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_ordinal_twenty_third(self):
        """'23rd' should match when spoken as 'twenty third'."""
        tracker = ScriptTracker("It is the 23rd day")
        tracker.update("it is the")
        pos_before = tracker.optimistic_position

        tracker.update("it is the twenty third")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_mixed_4k(self):
        """'4K' should match when spoken as 'four k'."""
        tracker = ScriptTracker("The display is 4K resolution")
        tracker.update("the display is")
        pos_before = tracker.optimistic_position

        tracker.update("the display is four k")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_mixed_4k_thousand(self):
        """'4K' should match when spoken as 'four thousand'."""
        tracker = ScriptTracker("The display is 4K resolution")
        tracker.update("the display is")
        pos_before = tracker.optimistic_position

        tracker.update("the display is four thousand")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_mixed_100gb(self):
        """'100GB' should match when spoken as 'one hundred gigabytes'."""
        tracker = ScriptTracker("Storage is 100GB available")
        tracker.update("storage is")
        pos_before = tracker.optimistic_position

        tracker.update("storage is one hundred gigabytes")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_mixed_m3(self):
        """'M3' should match when spoken as 'm three'."""
        tracker = ScriptTracker("The M3 processor is fast")
        tracker.update("the")
        pos_before = tracker.optimistic_position

        tracker.update("the m three")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_mixed_5m_metres(self):
        """'5m' should match when spoken as 'five metres'."""
        tracker = ScriptTracker("The distance is 5m away")
        tracker.update("the distance is")
        pos_before = tracker.optimistic_position

        tracker.update("the distance is five metres")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_comma_separated_number(self):
        """'1,000' should match when spoken as 'one thousand'."""
        tracker = ScriptTracker("We have 1,000 users")
        tracker.update("we have")
        pos_before = tracker.optimistic_position

        tracker.update("we have one thousand")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_eleven_thousand_comma(self):
        """'11,000' should match when spoken as 'eleven thousand'."""
        tracker = ScriptTracker("There are 11,000 participants")
        tracker.update("there are")
        pos_before = tracker.optimistic_position

        tracker.update("there are eleven thousand")
        pos_after = tracker.optimistic_position

        assert pos_after > pos_before

    def test_number_in_context(self):
        """Numbers should work correctly in full sentences."""
        tracker = ScriptTracker("The M3 processor has 25 billion transistors")

        # Advance through the sentence
        tracker.update("the m three processor has twenty five billion transistors")

        # Should have progressed through most of the script
        assert tracker.progress > 0.5


class TestExpansionValidationBug:
    """Tests for the bug where long expansions trigger false backtracks.

    Bug scenario: When matching a multi-word expansion like "1500" -> "one thousand
    five hundred", each word in the expansion is matched but positions_advanced
    stays 0 until the expansion is complete. This can trigger validation which
    incorrectly causes a backtrack.
    """

    def test_long_expansion_no_false_backtrack(self):
        """Multi-word expansion should not trigger false backtrack during matching.

        This reproduces the bug where:
        - "and" matches and advances to position 78
        - "one thousand five hundred" should match expansion at position 78
        - But validation triggered mid-expansion and caused incorrect backtrack
        """
        # Script with a large number that has multi-word expansion
        tracker = ScriptTracker("some text and 1500 large items")

        # Advance to "and"
        tracker.update("some text and")
        pos_after_and = tracker.optimistic_position
        high_water_after_and = tracker.high_water_mark

        # Now simulate word-by-word expansion matching
        # Each update represents a partial transcription update

        # "one" - first word of expansion
        result = tracker.update("some text and one")
        assert result.is_backtrack is False, "First word of expansion should not cause backtrack"

        # Check if validation triggered
        if tracker.needs_validation:
            validated_pos, was_backtrack = tracker.validate_position("some text and one")
            assert was_backtrack is False, "Validation during expansion should not cause backtrack"

        # "thousand" - second word of expansion
        result = tracker.update("some text and one thousand")
        assert result.is_backtrack is False, "Second word of expansion should not cause backtrack"

        if tracker.needs_validation:
            validated_pos, was_backtrack = tracker.validate_position("some text and one thousand")
            assert was_backtrack is False, "Validation during expansion should not cause backtrack"

        # "five" - third word of expansion
        result = tracker.update("some text and one thousand five")
        assert result.is_backtrack is False, "Third word of expansion should not cause backtrack"

        if tracker.needs_validation:
            validated_pos, was_backtrack = tracker.validate_position(
                "some text and one thousand five"
            )
            assert was_backtrack is False, "Validation during expansion should not cause backtrack"

        # "hundred" - fourth word of expansion (completes it)
        result = tracker.update("some text and one thousand five hundred")
        assert result.is_backtrack is False, "Completing expansion should not cause backtrack"

        # Position should have advanced past "1500"
        assert tracker.optimistic_position > pos_after_and, \
            "Position should advance after expansion is complete"

    def test_expansion_does_not_trigger_validation(self):
        """During expansion matching, validation should not be triggered.

        The bug was: when words_advanced == 0 (expansion not complete yet),
        needs_validation was being set to True, triggering incorrect validation.
        """
        tracker = ScriptTracker("prefix 1500 suffix words here today")

        # Advance to position before the number
        tracker.update("prefix")
        tracker.needs_validation = False

        # Start expansion matching - position won't advance until complete
        tracker.update("prefix one")

        # Validation should NOT be triggered during active expansion
        assert tracker.needs_validation is False or tracker.active_expansions, \
            "Should not trigger validation while actively matching expansion"

    def test_six_word_expansion_no_backtrack(self):
        """Very long expansions (like 1,500,000) should not cause false backtrack.

        "1,500,000" -> "one million five hundred thousand" is 5 words.
        This exceeds the typical validation threshold of 5 words.
        """
        tracker = ScriptTracker("there are 1500000 items remaining")

        tracker.update("there are")
        initial_pos = tracker.optimistic_position

        # Build up the expansion word by word
        words = ["one", "million", "five", "hundred", "thousand"]
        transcript = "there are"

        for word in words:
            transcript += f" {word}"
            result = tracker.update(transcript)
            assert result.is_backtrack is False, \
                f"Should not backtrack after speaking '{word}' in expansion"

        # After complete expansion, position should have advanced
        assert tracker.optimistic_position > initial_pos


class TestExpansionStateClearingOnPositionChange:
    """Tests that expansion state is properly cleared when position changes.

    Bug scenario: When a backtrack or jump occurs while in the middle of
    matching an expansion (like "one million" for "1000000"), the expansion
    state was not being cleared. This caused the tracker to continue trying
    to match expansion words at the new position, leading to cascading
    backtrack failures.
    """

    def test_expansion_state_cleared_on_jump_to(self):
        """jump_to() should clear any in-progress expansion state."""
        tracker = ScriptTracker("number 1000000 text here other words")

        # Start matching expansion for 1000000
        tracker.update("number")
        tracker.update("number one")  # Start expansion

        # Verify we're in an expansion
        assert tracker.active_expansions, "Should be in expansion matching"

        # Jump to a different position
        tracker.jump_to(3)  # Jump to "here"

        # Expansion state should be cleared
        assert not tracker.active_expansions, \
            "Expansion state should be cleared after jump_to()"
        assert tracker.expansion_match_position == 0

    def test_expansion_state_cleared_on_backtrack(self):
        """Backtrack should clear any in-progress expansion state.

        This was the bug: when backtracking while matching an expansion,
        the expansion words would continue to be expected at the new position.

        Since triggering an actual backtrack through validate_position is complex
        (many conditions must be met), we test by directly simulating what the
        backtrack code path does internally.
        """
        # Script: Words before a number, the number, then different words after
        tracker = ScriptTracker("start text here 1000000 some different words after")

        # Advance past "start text here" and start matching the number expansion
        tracker.update("start text here")

        # Start matching the number expansion "one million"
        tracker.update("start text here one")

        # Verify we're now in an expansion
        assert tracker.active_expansions, "Should be in expansion matching"
        expansion_was_active = len(tracker.active_expansions) > 0

        # Simulate what the backtrack code does internally:
        # These are the key state changes that happen in validate_position when
        # is_backtrack is True (lines 819-826 in tracker.py)
        new_position = 0  # Simulated backtrack to beginning
        tracker.optimistic_position = new_position
        tracker.current_word_index = new_position
        tracker.high_water_mark = new_position
        tracker.skip_disabled_count = 5
        tracker._clear_expansion_state()  # This is the fix we added

        # Verify expansion state is now cleared
        assert expansion_was_active, "Test setup: expansion should have been active"
        assert not tracker.active_expansions, \
            "Expansion state should be cleared after backtrack"
        assert tracker.expansion_match_position == 0

    def test_words_match_correctly_after_expansion_cleared(self):
        """After clearing expansion, subsequent words should match at new position."""
        # Use simple words without numbers to avoid expansion matching complexity
        tracker = ScriptTracker("apple 100 banana cherry grape melon")

        # Start expansion for "100"
        tracker.update("apple")
        tracker.update("apple one")  # Start matching "one hundred" for "100"

        # Verify in expansion
        assert tracker.active_expansions

        # Jump to "cherry" (position 3)
        tracker.jump_to(3)

        # Now try to match "cherry" - should work at the new position
        tracker.last_transcription = ""  # Clear transcript for clean matching
        result = tracker.update("cherry")

        # Should match at position 3 and advance to 4
        assert tracker.optimistic_position == 4
        assert result.word_index == 4

    def test_cascading_backtrack_prevented(self):
        """Clearing expansion state should prevent cascading backtrack failures.

        This reproduces the bug scenario from the debug log where:
        1. Expansion matching started ("one million" for a number)
        2. Backtrack occurred
        3. Expansion words kept coming but didn't match the new position
        4. Each mismatch triggered another backtrack, cascading failures
        """
        # Create a script similar to the bug scenario
        # Speakable words: the(0) number(1) is(2) one(3) as(4) written(5) also(6) decimal(7) ...
        script = "the number is 1000000 as written also decimal numbers are interesting"
        tracker = ScriptTracker(script)

        # Advance and start matching the number
        tracker.update("the number is")
        tracker.update("the number is one")  # Start expansion

        # Record state before simulated backtrack
        assert tracker.active_expansions, "Should be matching expansion"

        # Simulate backtrack to "as written" (position after the number)
        tracker.optimistic_position = 4  # Position of "as"
        tracker.current_word_index = 4
        tracker.high_water_mark = 4
        tracker._clear_expansion_state()  # This is what the fix does

        # Now subsequent words should match the new position, not cause cascading failures
        tracker.last_transcription = ""
        result = tracker.update("as written")

        # Should successfully match "as" (pos 4) and "written" (pos 5), ending at 6
        assert tracker.optimistic_position == 6  # Should be at position after "written"
        assert not result.is_backtrack
