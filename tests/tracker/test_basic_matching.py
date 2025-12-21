"""
Tests for basic word matching functionality in ScriptTracker.
"""

import pytest
from src.autocue.tracker import ScriptTracker, ScriptPosition


class TestOptimisticWordMatching:
    """Tests for word-by-word optimistic matching."""

    def test_single_word_advancement(self):
        """Each spoken word should advance position by 1."""
        tracker = ScriptTracker("The quick brown fox")

        pos1 = tracker.update("the")
        assert pos1.word_index == 1
        assert pos1.confidence == 100.0

        pos2 = tracker.update("the quick")
        assert pos2.word_index == 2

        pos3 = tracker.update("the quick brown")
        assert pos3.word_index == 3

        pos4 = tracker.update("the quick brown fox")
        assert pos4.word_index == 4

    def test_initial_position_is_zero(self):
        """Tracker should start at position 0."""
        tracker = ScriptTracker("hello world")
        assert tracker.optimistic_position == 0
        assert tracker.current_word_index == 0

    def test_empty_transcription_no_change(self):
        """Empty transcription should not change position."""
        tracker = ScriptTracker("hello world")
        tracker.update("hello")
        pos_before = tracker.optimistic_position

        tracker.update("")
        assert tracker.optimistic_position == pos_before

        tracker.update("   ")
        assert tracker.optimistic_position == pos_before


class TestWordSkipping:
    """Tests for handling skipped words."""

    def test_skip_one_word(self):
        """Should handle speaker skipping one word."""
        tracker = ScriptTracker("The quick brown fox")

        tracker.update("the")
        # Speaker says "brown" skipping "quick"
        pos = tracker.update("the brown")
        # Should advance past both "quick" (skipped) and "brown" (matched)
        assert pos.word_index == 3

    def test_skip_two_words(self):
        """Should handle speaker skipping two words."""
        tracker = ScriptTracker("The quick brown fox jumps")

        tracker.update("the")
        # Speaker says "fox" skipping "quick" and "brown"
        pos = tracker.update("the fox")
        # Should advance past "quick", "brown" (skipped) and "fox" (matched)
        assert pos.word_index == 4

    def test_no_match_after_max_skip(self):
        """Should not advance if word doesn't match within skip range."""
        tracker = ScriptTracker("The quick brown fox jumps over")

        tracker.update("the")
        initial_pos = tracker.optimistic_position

        # "over" is too far ahead (4 words), shouldn't match
        pos = tracker.update("the over")
        # Position should only advance for "the", not "over"
        assert pos.word_index == initial_pos


class TestFuzzyWordMatching:
    """Tests for fuzzy matching of individual words."""

    def test_case_insensitive_matching(self):
        """Should match words regardless of case."""
        tracker = ScriptTracker("The Quick Brown Fox")

        pos = tracker.update("THE QUICK BROWN")
        assert pos.word_index == 3

    def test_fuzzy_match_similar_words(self):
        """Should match words with minor differences."""
        tracker = ScriptTracker("recognize the pattern")

        # "recognise" (British spelling) should match "recognize"
        pos = tracker.update("recognise")
        assert pos.word_index == 1

    def test_punctuation_ignored(self):
        """Punctuation should be ignored in matching."""
        tracker = ScriptTracker("Hello, world! How are you?")

        pos = tracker.update("hello world how")
        assert pos.word_index == 3


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_script(self):
        """Should handle empty script gracefully."""
        tracker = ScriptTracker("")
        assert tracker.words == []
        assert tracker.progress == 0.0

    def test_single_word_script(self):
        """Should handle single word script."""
        tracker = ScriptTracker("hello")

        pos = tracker.update("hello")
        assert pos.word_index == 1
        assert tracker.progress == 1.0

    def test_position_beyond_script(self):
        """Should not advance beyond script length."""
        tracker = ScriptTracker("hello world")

        tracker.update("hello world extra words here")
        assert tracker.optimistic_position <= len(tracker.words)
