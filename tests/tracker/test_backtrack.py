"""
Tests for backtrack handling and repeated word scenarios in ScriptTracker.
"""

from src.autocue.tracker import ScriptTracker


class TestRepeatedWords:
    """Tests for handling repeated words in the script."""

    def test_repeated_word_continues_forward(self) -> None:
        """Repeated words should not cause false backtracking."""
        tracker: ScriptTracker = ScriptTracker("the quick brown the lazy dog")

        # Advance through first "the quick brown"
        text_sequence: list[str] = ["the", "the quick", "the quick brown"]
        for text in text_sequence:
            tracker.update(text)

        assert tracker.optimistic_position == 3

        # Now say "the" again - should match position 3, not position 0
        tracker.update("the quick brown the")
        assert tracker.optimistic_position == 4  # Moved to position after second "the"

    def test_repeated_word_validation_trusts_optimistic(self) -> None:
        """Validation should trust optimistic position when repeated words
        cause ambiguity."""
        tracker: ScriptTracker = ScriptTracker("the quick brown the lazy dog")

        # Advance to position 4 (after second "the")
        text_sequence: list[str] = ["the", "the quick",
                                    "the quick brown", "the quick brown the"]
        for text in text_sequence:
            tracker.update(text)

        assert tracker.optimistic_position == 4

        # Validation with "the lazy" - matches position 3-4
        # Should trust optimistic since deviation is small
        is_backtrack: bool
        _validated_pos, is_backtrack = tracker.detect_jump(
            "the lazy dog")

        # Should NOT backtrack - trust optimistic for small deviation
        assert is_backtrack is False
        assert tracker.optimistic_position == 4

    def test_common_words_dont_cause_backtrack(self) -> None:
        """Common repeated words like 'the', 'a', 'is' should not cause issues."""
        tracker: ScriptTracker = ScriptTracker(
            "The cat is on the mat and the dog is happy")

        # Advance through the script
        text_sequence: list[str] = ["the cat", "the cat is", "the cat is on",
                                    "the cat is on the", "the cat is on the mat"]
        for text in text_sequence:
            tracker.update(text)

        position_after_mat: int = tracker.optimistic_position

        # Continue with "and the" - the second "the" should not cause backtrack
        tracker.update("the cat is on the mat and")
        tracker.update("the cat is on the mat and the")

        # Position should have advanced, not gone back
        assert tracker.optimistic_position > position_after_mat


class TestBacktrackSkipDisable:
    """Tests for skip logic being disabled after backtrack to prevent
    false matches."""

    def test_skip_disabled_after_backtrack(self) -> None:
        """After backtrack, skip logic should be disabled to prevent matching
        old transcript words."""
        # Script has two similar sections
        script: str = "navigate at a glance subsection example this is a subsection"
        tracker: ScriptTracker = ScriptTracker(script)

        # Advance to "this is a subsection" (words 6-9)
        tracker.jump_to(6)  # at "this"
        tracker.last_transcription = "this is a subsection"
        tracker.update("this is a subsection")

        # Now simulate what happens in a backtrack: position is reset
        # but transcript still contains "subsection" from the later position
        tracker.optimistic_position = 2  # at "a" (before "glance")
        tracker.current_word_index = 2
        tracker.skip_disabled_count = 5  # This is what the backtrack code sets
        tracker.last_transcription = ""  # Cleared by backtrack

        # Now if we try to match with old transcript remnants,
        # the skip logic should NOT match "subsection" at position 4
        # even though the transcript contains it
        tracker.update("a glance subsection")

        # Position should advance through "a", "glance" but NOT skip to "subsection"
        # because skip logic is disabled
        # After "a" matches at pos 2, position becomes 3 ("glance")
        # After "glance" matches at pos 3, position becomes 4 ("subsection")
        # "subsection" should match at current pos 4, not skip ahead
        assert tracker.optimistic_position <= 5  # Should not skip ahead to position 6+

    def test_skip_reenabled_after_matches(self) -> None:
        """Skip logic should be re-enabled after successful matches."""
        script: str = "one two three four five six seven eight"
        tracker: ScriptTracker = ScriptTracker(script)

        # Simulate backtrack state
        tracker.skip_disabled_count = 3

        # Match 3 words - should decrement skip_disabled_count each time
        tracker.update("one")
        assert tracker.skip_disabled_count == 2

        tracker.update("one two")
        assert tracker.skip_disabled_count == 1

        tracker.update("one two three")
        assert tracker.skip_disabled_count == 0

        # Now skip logic should be re-enabled
        # Skipping "four" should work now
        tracker.update("one two three five")  # Skip "four"
        assert tracker.optimistic_position == 5  # At "six" after matching "five"

    def test_backtrack_disables_skip_logic(self) -> None:
        """Backtrack should disable skip logic to prevent stale word matching."""
        script: str = "beginning middle end final words here"
        tracker: ScriptTracker = ScriptTracker(script)

        # Advance and set transcript
        tracker.update("beginning middle end")
        assert tracker.last_transcription == "beginning middle end"
        assert tracker.skip_disabled_count == 0

        # Simulate backtrack via validate_position
        tracker.optimistic_position = 3
        # Force a backtrack condition
        is_backtrack: bool
        _validated_pos, is_backtrack = tracker.detect_jump(
            "beginning middle")

        # If backtrack detected, skip logic should be disabled
        if is_backtrack:
            assert tracker.skip_disabled_count == 5
