"""
Tests for validation triggering and backtrack detection in ScriptTracker.
"""

import pytest
from src.autocue.tracker import ScriptTracker


class TestValidationTriggering:
    """Tests for validation triggering logic."""

    def test_validation_triggers_after_five_words(self):
        """Validation should be needed after 5 words spoken."""
        tracker = ScriptTracker("one two three four five six seven eight")

        assert tracker.needs_validation is False

        # Speak 4 words - no validation yet
        for text in ["one", "one two", "one two three", "one two three four"]:
            tracker.update(text)
        assert tracker.needs_validation is False

        # 5th word triggers validation
        tracker.update("one two three four five")
        assert tracker.needs_validation is True

    def test_validation_resets_counter(self):
        """Validation should reset the word counter."""
        tracker = ScriptTracker("one two three four five six seven eight nine ten")

        # Trigger validation
        for text in ["one", "one two", "one two three", "one two three four",
                     "one two three four five"]:
            tracker.update(text)
        assert tracker.needs_validation is True

        # Run validation
        tracker.validate_position("one two three four five")
        assert tracker.needs_validation is False
        assert tracker.words_since_validation == 0


class TestBacktrackDetection:
    """Tests for backtrack detection via validation."""

    def test_backtrack_detected_significant_deviation(self):
        """Should detect backtrack only when deviation is significant (>2 words)."""
        tracker = ScriptTracker(
            "The quick brown fox jumps over the lazy dog sits quietly"
        )

        # Advance to word 8 (dog)
        for text in ["the", "the quick", "the quick brown", "the quick brown fox",
                     "the quick brown fox jumps", "the quick brown fox jumps over",
                     "the quick brown fox jumps over the",
                     "the quick brown fox jumps over the lazy"]:
            tracker.update(text)

        assert tracker.optimistic_position == 8
        assert tracker.high_water_mark == 8

        # Simulate a real backtrack - user restarts with completely different words
        # that match the beginning of the script, not near position 8
        tracker.needs_validation = True
        validated_pos, is_backtrack = tracker.validate_position("the quick brown")

        assert is_backtrack is True
        # Position should be reset to match "the quick brown" (near position 0-3)
        assert tracker.optimistic_position < 5

    def test_no_backtrack_for_forward_movement(self):
        """Forward movement should not trigger backtrack."""
        tracker = ScriptTracker("The quick brown fox")

        tracker.update("the quick")
        tracker.needs_validation = True
        validated_pos, is_backtrack = tracker.validate_position("the quick brown")

        assert is_backtrack is False

    def test_no_backtrack_for_small_deviation(self):
        """Small deviations (<=2 words) should not trigger corrections."""
        tracker = ScriptTracker("The quick brown fox jumps over the lazy dog")

        # Advance to position 4 (after "fox")
        for text in ["the", "the quick", "the quick brown", "the quick brown fox"]:
            tracker.update(text)

        assert tracker.optimistic_position == 4

        # Force validation with transcript that matches around position 3-4
        # (small deviation from optimistic position of 4)
        tracker.needs_validation = True
        validated_pos, is_backtrack = tracker.validate_position(
            "quick brown fox jumps"
        )

        assert is_backtrack is False
        # Position should stay at 4 (trust optimistic for <=2 word deviation)
        assert tracker.optimistic_position == 4
