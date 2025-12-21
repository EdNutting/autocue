"""
Tests for filler word handling in ScriptTracker.
"""

from src.autocue.tracker import ScriptPosition, ScriptTracker


class TestFillerWordHandling:
    """Tests for filler word detection and handling."""

    def test_filler_word_skipped_when_not_in_script(self) -> None:
        """Filler words like 'um' should be skipped when not in script."""
        tracker: ScriptTracker = ScriptTracker("The quick brown fox")

        # "um" is a filler and not in script - should be skipped
        pos: ScriptPosition = tracker.update("the um quick")
        # Should advance for "the" and "quick", skipping "um"
        assert pos.word_index == 2

    def test_filler_word_matches_when_in_script(self) -> None:
        """Filler words should match when they ARE in the script.

        This is the bug fix: 'like' was being skipped even when
        the script contained 'like' at the current position.
        """
        tracker: ScriptTracker = ScriptTracker("I like cats")

        pos1: ScriptPosition = tracker.update("i")
        assert pos1.word_index == 1  # Passed "i"

        # "like" is in FILLER_WORDS but also in the script at position 1
        # It should match, not be skipped
        pos2: ScriptPosition = tracker.update("i like")
        assert pos2.word_index == 2  # Passed "like"

        pos3: ScriptPosition = tracker.update("i like cats")
        assert pos3.word_index == 3  # Passed "cats"

    def test_so_matches_when_in_script(self) -> None:
        """'so' is a filler word but should match when in script."""
        tracker: ScriptTracker = ScriptTracker("So what do you think")

        pos: ScriptPosition = tracker.update("so what")
        # "so" should match, not be skipped
        assert pos.word_index == 2

    def test_well_matches_when_in_script(self) -> None:
        """'well' is a filler word but should match when in script."""
        tracker: ScriptTracker = ScriptTracker("The well was deep")

        pos1: ScriptPosition = tracker.update("the")
        assert pos1.word_index == 1

        pos2: ScriptPosition = tracker.update("the well")
        # "well" should match "well" in the script
        assert pos2.word_index == 2
