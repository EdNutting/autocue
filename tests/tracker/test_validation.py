# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Tests for validation triggering and backtrack detection in ScriptTracker.
"""

from src.autocue.tracker import ScriptTracker


class TestValidationTriggering:
    """Tests for validation triggering logic."""

    def test_validation_triggers_after_five_words(self) -> None:
        """Validation should be needed after 5 words spoken."""
        tracker: ScriptTracker = ScriptTracker(
            "one two three four five six seven eight")

        tracker.jump_threshold = 5
        assert tracker.allow_jump_detection is False

        # Speak 4 words - no validation yet
        texts: list[str] = ["one", "one two",
                            "one two three", "one two three four"]
        for text in texts:
            tracker.update(text)
        assert tracker.allow_jump_detection is False

        # 5th word triggers validation
        tracker.update("one two three four five")
        assert tracker.allow_jump_detection is True

    def test_validation_resets_counter(self) -> None:
        """Validation should reset the word counter."""
        tracker: ScriptTracker = ScriptTracker(
            "one two three four five six seven eight nine ten")

        # Trigger validation
        texts: list[str] = ["one", "one two", "one two three", "one two three four",
                            "one two three four five"]
        for text in texts:
            tracker.update(text)
        assert tracker.allow_jump_detection is True

        # Run validation
        tracker.detect_jump("one two three four five")
        assert tracker.allow_jump_detection is False
        assert tracker.words_since_validation == 0


class TestBacktrackDetection:
    """Tests for backtrack detection via validation."""

    def test_backtrack_detected_significant_deviation(self) -> None:
        """Should detect backtrack only when deviation is significant (>2 words)."""
        tracker: ScriptTracker = ScriptTracker(
            "The quick brown fox jumps over the lazy dog sits quietly"
        )

        # Advance to word 8 (dog)
        texts: list[str] = ["the", "the quick", "the quick brown", "the quick brown fox",
                            "the quick brown fox jumps", "the quick brown fox jumps over",
                            "the quick brown fox jumps over the",
                            "the quick brown fox jumps over the lazy"]
        for text in texts:
            tracker.update(text)

        assert tracker.optimistic_position == 8

        # Simulate a real backtrack - user restarts with completely different words
        # that match the beginning of the script, not near position 8
        is_backtrack: bool
        _validated_pos, is_backtrack = tracker.detect_jump(
            "the quick brown")

        assert is_backtrack is True
        # Position should be reset to match "the quick brown" (near position 0-3)
        assert tracker.optimistic_position < 5

    def test_no_backtrack_for_forward_movement(self) -> None:
        """Forward movement should not trigger backtrack."""
        tracker: ScriptTracker = ScriptTracker("The quick brown fox")

        tracker.update("the quick")
        is_backtrack: bool
        _validated_pos, is_backtrack = tracker.detect_jump(
            "the quick brown")

        assert is_backtrack is False

    def test_no_backtrack_for_small_deviation(self) -> None:
        """Small deviations (<=2 words) should not trigger corrections."""
        tracker: ScriptTracker = ScriptTracker(
            "The quick brown fox jumps over the lazy dog")

        # Advance to position 4 (after "fox")
        texts: list[str] = ["the", "the quick",
                            "the quick brown", "the quick brown fox"]
        for text in texts:
            tracker.update(text)

        assert tracker.optimistic_position == 4

        # Force validation with transcript that matches around position 3-4
        # (small deviation from optimistic position of 4)
        is_backtrack: bool
        _validated_pos, is_backtrack = tracker.detect_jump(
            "quick brown fox jumps"
        )

        assert is_backtrack is False
        # Position should stay at 4 (trust optimistic for <=2 word deviation)
        assert tracker.optimistic_position == 4
