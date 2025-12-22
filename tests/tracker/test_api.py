# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Tests for ScriptTracker API methods (reset, jump, extract, display).
"""

from src.autocue.tracker import ScriptLine, ScriptTracker


class TestResetAndJump:
    """Tests for reset and jump functionality."""

    def test_reset_clears_all_state(self) -> None:
        """Reset should clear all tracking state."""
        tracker: ScriptTracker = ScriptTracker("hello world test")

        tracker.update("hello world")
        assert tracker.optimistic_position > 0

        tracker.reset()

        assert tracker.optimistic_position == 0
        assert tracker.current_word_index == 0
        assert tracker.committed_state.last_transcription == ""
        assert tracker.words_since_validation == 0

    def test_jump_to_position(self) -> None:
        """Jump should set position and sync state."""
        tracker: ScriptTracker = ScriptTracker("one two three four five")

        tracker.jump_to(3)

        assert tracker.optimistic_position == 3
        assert tracker.current_word_index == 3
        assert tracker.committed_state.last_transcription == ""

    def test_jump_clamps_to_valid_range(self) -> None:
        """Jump should clamp to valid word indices."""
        tracker: ScriptTracker = ScriptTracker("one two three")

        tracker.jump_to(100)
        assert tracker.optimistic_position == 2  # Last valid index

        tracker.jump_to(-5)
        assert tracker.optimistic_position == 0


class TestExtractNewWords:
    """Tests for extracting new words from transcription."""

    def test_extract_new_words_extending_prefix(self) -> None:
        """Should extract only new words when extending previous."""
        tracker: ScriptTracker = ScriptTracker("the quick brown fox")

        tracker.update("the quick")
        new_words: list[str] = tracker.extract_new_words("the quick brown", tracker.committed_state)

        assert new_words == ["brown"]

    def test_extract_new_words_fresh_start(self) -> None:
        """Should handle completely new transcription."""
        tracker: ScriptTracker = ScriptTracker("the quick brown fox")

        # First transcription
        new_words: list[str] = tracker.extract_new_words("hello world", tracker.committed_state)
        assert len(new_words) > 0

    def test_extract_new_words_no_match(self) -> None:
        """Should return recent words when no prefix match."""
        tracker: ScriptTracker = ScriptTracker("the quick brown fox")
        tracker.committed_state.last_transcription = "completely different"

        new_words: list[str] = tracker.extract_new_words(
            "hello world testing", tracker.committed_state)
        # Should return all words when no prefix match
        assert new_words == ["hello", "world", "testing"]


class TestDisplayMethods:
    """Tests for display-related methods."""

    def test_get_display_lines(self) -> None:
        """Should return correct lines around current position."""
        script: str = "Line one.\nLine two.\nLine three.\nLine four."
        tracker: ScriptTracker = ScriptTracker(script)

        # Move to line 2
        tracker.update("line one line two")

        lines: list[ScriptLine]
        current_idx: int
        lines, current_idx, _word_offset = tracker.get_display_lines(
            past_lines=1, future_lines=2)

        assert len(lines) > 0
        assert current_idx >= 0

    def test_progress_property(self) -> None:
        """Progress should reflect position through script."""
        tracker: ScriptTracker = ScriptTracker("one two three four")

        assert tracker.progress == 0.0

        tracker.update("one two")
        assert 0.0 < tracker.progress < 1.0

        tracker.update("one two three four")
        assert tracker.progress == 1.0
