"""Tests for tracker and transcriber reset behavior when prompting starts."""

from unittest.mock import Mock, AsyncMock, patch
import pytest

from src.autocue.tracker import ScriptTracker


class TestPromptingReset:
    """Test that tracker and transcriber are reset when prompting starts."""

    @pytest.mark.asyncio
    async def test_tracker_reset_on_prompting_start(self):
        """Verify that tracker is reset to position 0 when prompting starts."""
        # Create a tracker and advance it to a non-zero position
        tracker = ScriptTracker("hello world this is a test script")

        # Simulate tracking some words
        tracker.update("hello world this")
        initial_position = tracker.current_position

        # Verify we've moved forward
        assert initial_position.word_index > 0

        # Reset the tracker (simulating what happens when prompting starts)
        tracker.reset()

        # Verify position is back to 0
        assert tracker.current_position.word_index == 0
        assert tracker.current_word_index == 0

    @pytest.mark.asyncio
    async def test_tracker_state_cleared_on_reset(self):
        """Verify that all tracker state is cleared when reset."""
        tracker = ScriptTracker("hello world this is a test script")

        # Simulate some tracking activity
        tracker.update("hello world")
        tracker.update("hello world this is")

        # Verify state has accumulated
        assert tracker.current_word_index > 0
        assert tracker.words_since_validation > 0

        # Reset
        tracker.reset()

        # Verify all state is cleared
        assert tracker.current_word_index == 0
        assert tracker.words_since_validation == 0
        assert tracker.skip_disabled_count == 0
        assert tracker.committed_state.optimistic_position == 0
        assert tracker.committed_state.last_transcription == ""

    @pytest.mark.asyncio
    async def test_tracker_can_track_after_reset(self):
        """Verify that tracker can continue tracking after reset."""
        tracker = ScriptTracker("hello world this is a test")

        # First tracking session
        tracker.update("hello world")
        first_position = tracker.current_position
        assert first_position.word_index > 0

        # Reset
        tracker.reset()
        assert tracker.current_position.word_index == 0

        # Second tracking session - should work normally
        tracker.update("hello world")
        second_position = tracker.current_position

        # Should track to the same position as before
        assert second_position.word_index == first_position.word_index

    @pytest.mark.asyncio
    async def test_transcriber_reset_clears_buffer(self):
        """Verify that transcriber reset clears any buffered audio state."""
        from src.autocue.transcribe import Transcriber
        from unittest.mock import Mock

        # Create a mock provider
        mock_provider = Mock()
        mock_provider.reset = Mock()

        # Create transcriber with mocked provider
        with patch('src.autocue.transcribe.create_provider', return_value=mock_provider):
            transcriber = Transcriber(model_name="test-model")

            # Reset the transcriber
            transcriber.reset()

            # Verify provider's reset was called
            mock_provider.reset.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
