"""
Tests for basic word matching functionality in ScriptTracker.
"""

from typing import List

import pytest
from src.autocue.tracker import ScriptTracker, ScriptPosition


class TestOptimisticWordMatching:
    """Tests for word-by-word optimistic matching."""

    def test_single_word_advancement(self) -> None:
        """Each spoken word should advance position by 1."""
        tracker: ScriptTracker = ScriptTracker("The quick brown fox")

        pos1: ScriptPosition = tracker.update("the")
        assert pos1.word_index == 1
        assert pos1.confidence == 100.0

        pos2: ScriptPosition = tracker.update("the quick")
        assert pos2.word_index == 2

        pos3: ScriptPosition = tracker.update("the quick brown")
        assert pos3.word_index == 3

        pos4: ScriptPosition = tracker.update("the quick brown fox")
        assert pos4.word_index == 4

    def test_initial_position_is_zero(self) -> None:
        """Tracker should start at position 0."""
        tracker: ScriptTracker = ScriptTracker("hello world")
        assert tracker.optimistic_position == 0
        assert tracker.current_word_index == 0

    def test_empty_transcription_no_change(self) -> None:
        """Empty transcription should not change position."""
        tracker: ScriptTracker = ScriptTracker("hello world")
        tracker.update("hello")
        pos_before: int = tracker.optimistic_position

        tracker.update("")
        assert tracker.optimistic_position == pos_before

        tracker.update("   ")
        assert tracker.optimistic_position == pos_before


class TestWordSkipping:
    """Tests for handling skipped words."""

    def test_skip_one_word(self) -> None:
        """Should handle speaker skipping one word."""
        tracker: ScriptTracker = ScriptTracker("The quick brown fox")

        tracker.update("the")
        # Speaker says "brown" skipping "quick"
        pos: ScriptPosition = tracker.update("the brown")
        # Should advance past both "quick" (skipped) and "brown" (matched)
        assert pos.word_index == 3

    def test_skip_two_words(self) -> None:
        """Should handle speaker skipping two words."""
        tracker: ScriptTracker = ScriptTracker("The quick brown fox jumps")

        tracker.update("the")
        # Speaker says "fox" skipping "quick" and "brown"
        pos: ScriptPosition = tracker.update("the fox")
        # Should advance past "quick", "brown" (skipped) and "fox" (matched)
        assert pos.word_index == 4

    def test_no_match_after_max_skip(self) -> None:
        """Should not advance if word doesn't match within skip range."""
        tracker: ScriptTracker = ScriptTracker(
            "The quick brown fox jumps over")

        tracker.update("the")
        initial_pos: int = tracker.optimistic_position

        # "over" is too far ahead (4 words), shouldn't match
        pos: ScriptPosition = tracker.update("the over")
        # Position should only advance for "the", not "over"
        assert pos.word_index == initial_pos


class TestFuzzyWordMatching:
    """Tests for fuzzy matching of individual words."""

    def test_case_insensitive_matching(self) -> None:
        """Should match words regardless of case."""
        tracker: ScriptTracker = ScriptTracker("The Quick Brown Fox")

        pos: ScriptPosition = tracker.update("THE QUICK BROWN")
        assert pos.word_index == 3

    def test_fuzzy_match_similar_words(self) -> None:
        """Should match words with minor differences."""
        tracker: ScriptTracker = ScriptTracker("recognize the pattern")

        # "recognise" (British spelling) should match "recognize"
        pos: ScriptPosition = tracker.update("recognise")
        assert pos.word_index == 1

    def test_punctuation_ignored(self) -> None:
        """Punctuation should be ignored in matching."""
        tracker: ScriptTracker = ScriptTracker("Hello, world! How are you?")

        pos: ScriptPosition = tracker.update("hello world how")
        assert pos.word_index == 3


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_script(self) -> None:
        """Should handle empty script gracefully."""
        tracker: ScriptTracker = ScriptTracker("")
        words: List[str] = tracker.words
        assert words == []
        assert tracker.progress == 0.0

    def test_single_word_script(self) -> None:
        """Should handle single word script."""
        tracker: ScriptTracker = ScriptTracker("hello")

        pos: ScriptPosition = tracker.update("hello")
        assert pos.word_index == 1
        assert tracker.progress == 1.0

    def test_position_beyond_script(self) -> None:
        """Should not advance beyond script length."""
        tracker: ScriptTracker = ScriptTracker("hello world")

        tracker.update("hello world extra words here")
        assert tracker.optimistic_position <= len(tracker.words)
