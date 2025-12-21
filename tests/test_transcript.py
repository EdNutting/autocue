"""Tests for the transcript saving functionality."""

import asyncio
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from autocue.main import AutocueApp, TRANSCRIPT_DIR


class TestTranscriptSaving:
    """Test the transcript saving functionality."""

    def test_transcript_disabled_by_default(self):
        """Transcript saving should be disabled by default."""
        app = AutocueApp()
        assert not app.save_transcript
        assert app.transcript_file is None

    def test_transcript_enabled_via_parameter(self):
        """Transcript saving can be enabled via constructor parameter."""
        app = AutocueApp(save_transcript=True)
        assert app.save_transcript
        # File not created until _start_transcript is called
        assert app.transcript_file is None

    def test_write_transcript_no_op_when_disabled(self):
        """_write_transcript() should do nothing when saving is disabled."""
        app = AutocueApp(save_transcript=False)
        # Should not raise even without transcript file
        app._write_transcript("test text", is_partial=False)

    def test_write_transcript_no_op_without_file(self):
        """_write_transcript() should do nothing without transcript file."""
        app = AutocueApp(save_transcript=True)
        # File not initialized
        app._write_transcript("test text", is_partial=False)
        # Should not raise


class TestDynamicTranscriptControl:
    """Test the dynamic start/stop transcript functionality."""

    @pytest.fixture
    def mock_server(self):
        """Create a mock server for testing."""
        server = mock.AsyncMock()
        server.send_transcript_status = mock.AsyncMock()
        return server

    @pytest.mark.asyncio
    async def test_start_transcript_creates_file(self, mock_server):
        """_start_transcript() should create a new transcript file."""
        app = AutocueApp(save_transcript=False)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch('autocue.main.TRANSCRIPT_DIR', Path(tmpdir)):
                await app._start_transcript()

                assert app.save_transcript is True
                assert app.transcript_file is not None
                assert app.transcript_file.exists()
                mock_server.send_transcript_status.assert_called_once()
                call_args = mock_server.send_transcript_status.call_args
                assert call_args[0][0] is True  # recording=True

    @pytest.mark.asyncio
    async def test_start_transcript_no_op_if_already_recording(self, mock_server):
        """_start_transcript() should be a no-op if already recording."""
        app = AutocueApp(save_transcript=True)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch('autocue.main.TRANSCRIPT_DIR', Path(tmpdir)):
                # Start first time
                await app._start_transcript()
                first_file = app.transcript_file

                # Reset mock
                mock_server.send_transcript_status.reset_mock()

                # Start again - should use same file
                await app._start_transcript()
                assert app.transcript_file == first_file
                # Should still send status update
                mock_server.send_transcript_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_transcript_closes_file(self, mock_server):
        """_stop_transcript() should close the transcript and clear state."""
        app = AutocueApp(save_transcript=False)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch('autocue.main.TRANSCRIPT_DIR', Path(tmpdir)):
                # Start recording
                await app._start_transcript()
                transcript_file = app.transcript_file

                # Stop recording
                await app._stop_transcript()

                assert app.save_transcript is False
                assert app.transcript_file is None

                # File should have end marker
                content = transcript_file.read_text()
                assert "Transcript ended" in content

                # Should send status update
                call_args = mock_server.send_transcript_status.call_args
                assert call_args[0][0] is False  # recording=False

    @pytest.mark.asyncio
    async def test_stop_transcript_no_op_if_not_recording(self, mock_server):
        """_stop_transcript() should be a no-op if not recording."""
        app = AutocueApp(save_transcript=False)
        app.server = mock_server

        await app._stop_transcript()

        assert app.save_transcript is False
        assert app.transcript_file is None
        mock_server.send_transcript_status.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_start_stop_cycle(self, mock_server):
        """Test starting and stopping transcript multiple times."""
        app = AutocueApp(save_transcript=False)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch('autocue.main.TRANSCRIPT_DIR', Path(tmpdir)):
                # First cycle
                await app._start_transcript()
                first_file = app.transcript_file
                app._write_transcript("first recording", is_partial=False)
                await app._stop_transcript()

                # Wait a moment to ensure different timestamp
                await asyncio.sleep(1.1)

                # Second cycle
                await app._start_transcript()
                second_file = app.transcript_file
                app._write_transcript("second recording", is_partial=False)
                await app._stop_transcript()

                # Files should be different (different timestamps)
                assert first_file != second_file
                assert first_file.exists()
                assert second_file.exists()

                # Content should be correct
                assert "first recording" in first_file.read_text()
                assert "second recording" in second_file.read_text()


class TestTranscriptTracking:
    """Tests for verifying the tracking system follows transcripts smoothly.

    These tests use real transcript data to verify that the tracker:
    1. Follows the script accurately when given transcript piece by piece
    2. Does not jump around unexpectedly
    3. Does not backtrack or forward jump excessively
    4. Handles differences between transcription and script gracefully
    """

    @pytest.fixture
    def number_test_script(self):
        """Load the number test script."""
        script_path = Path(__file__).parent.parent / "samples" / "number_test_script.md"
        return script_path.read_text()

    @pytest.fixture
    def number_test_transcript(self):
        """Load and parse the number test transcript, excluding start/end markers."""
        transcript_path = Path(__file__).parent.parent / "transcripts" / "transcript_20251221_000011.txt"
        lines = transcript_path.read_text().strip().split("\n")

        # Filter out the "Transcript started" and "Transcript ended" lines
        content_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith("===") or not line:
                continue
            content_lines.append(line)

        return content_lines

    def test_transcript_loads_correctly(self, number_test_transcript):
        """Verify transcript is loaded and parsed correctly."""
        assert len(number_test_transcript) > 0
        # First content line should be about "number expansion test"
        assert "number" in number_test_transcript[0].lower()

    def test_script_loads_correctly(self, number_test_script):
        """Verify script is loaded correctly."""
        assert len(number_test_script) > 0
        assert "Number Expansion Test Script" in number_test_script

    def test_smooth_tracking_word_by_word(self, number_test_script, number_test_transcript):
        """Verify tracking advances smoothly when feeding words one at a time.

        The tracking system should handle number format differences between
        transcription and script (e.g., "one hundred" vs "100") and advance
        smoothly through the script.
        """
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)

        # Build cumulative transcript word by word
        all_words = []
        for line in number_test_transcript:
            words = line.split()
            all_words.extend(words)

        max_jump = 0
        last_position = 0
        position_history = [0]

        # Feed every word to simulate word-by-word updates
        cumulative_text = ""
        for i, word in enumerate(all_words):
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            # Update with cumulative text (tracker compares with last_transcription)
            pos = tracker.update(cumulative_text)
            current_position = pos.speakable_index

            # Calculate jump size
            jump = current_position - last_position
            if abs(jump) > max_jump:
                max_jump = abs(jump)

            position_history.append(current_position)
            last_position = current_position

        # The maximum jump should be small (1-2 words typically, maybe 3 with skipping)
        # We allow up to 5 to account for skip-ahead matching
        assert max_jump <= 5, f"Maximum jump was {max_jump}, expected <= 5"

        # Position should have advanced significantly through the script
        final_progress = tracker.progress
        assert final_progress > 0.8, f"Final progress was {final_progress:.2%}, expected > 80%"

    def test_smooth_tracking_chunk_by_chunk(self, number_test_script, number_test_transcript):
        """Verify tracking advances smoothly when feeding transcript line by line (chunks).

        For chunk updates, jumps should be proportional to the number of words in the chunk.
        We verify that no jump exceeds the chunk size by more than a small margin.
        """
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)

        last_position = 0
        disproportionate_jumps = []

        # Feed transcript line by line (simulating chunks of speech)
        cumulative_text = ""
        for line in number_test_transcript:
            if cumulative_text:
                cumulative_text += " " + line
            else:
                cumulative_text = line

            chunk_word_count = len(line.split())
            pos = tracker.update(cumulative_text)
            current_position = pos.speakable_index

            # Calculate jump size
            jump = current_position - last_position

            # For chunk updates, jump should be approximately equal to chunk size
            # Allow some tolerance for skipped words or minor mismatches
            # A jump should not exceed 1.5x the chunk size (50% tolerance)
            max_reasonable_jump = max(5, int(chunk_word_count * 1.5))
            if jump > max_reasonable_jump:
                disproportionate_jumps.append((jump, chunk_word_count, line[:40]))

            last_position = current_position

        # There should be very few disproportionate jumps (validation corrections)
        assert len(disproportionate_jumps) <= 2, \
            f"Too many disproportionate jumps: {disproportionate_jumps}"

        # Position should have advanced significantly
        final_progress = tracker.progress
        assert final_progress > 0.8, f"Final progress was {final_progress:.2%}, expected > 80%"

    def test_no_backtracking(self, number_test_script, number_test_transcript):
        """Verify that tracking never goes backward unexpectedly."""
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)

        high_water_mark = 0
        backtrack_count = 0
        largest_backtrack = 0

        # Feed transcript word by word
        all_words = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text = ""
        for word in all_words:
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            pos = tracker.update(cumulative_text)
            current_position = pos.speakable_index

            if current_position < high_water_mark:
                backtrack_amount = high_water_mark - current_position
                backtrack_count += 1
                if backtrack_amount > largest_backtrack:
                    largest_backtrack = backtrack_amount
            else:
                high_water_mark = current_position

        # There should be no backtracks (or very few, very small ones)
        assert largest_backtrack <= 2, f"Largest backtrack was {largest_backtrack} words, expected <= 2"
        # Allow a few small backtracks due to speech recognition differences
        assert backtrack_count <= 3, f"Backtrack count was {backtrack_count}, expected <= 3"

    def test_no_forward_jumps(self, number_test_script, number_test_transcript):
        """Verify that tracking never jumps forward unexpectedly."""
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)

        large_jump_count = 0
        largest_forward_jump = 0

        # Feed transcript word by word
        all_words = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text = ""
        last_position = 0

        for word in all_words:
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            pos = tracker.update(cumulative_text)
            current_position = pos.speakable_index

            forward_jump = current_position - last_position

            # Count jumps larger than 2 (normal matching might skip 1-2 words)
            if forward_jump > 2:
                large_jump_count += 1
                if forward_jump > largest_forward_jump:
                    largest_forward_jump = forward_jump

            last_position = current_position

        # Large forward jumps should be rare
        # We allow some due to word skipping (speaker skips a word)
        assert largest_forward_jump <= 5, f"Largest forward jump was {largest_forward_jump} words, expected <= 5"
        # Most updates should advance by 0-2 words
        total_updates = len(all_words)
        jump_ratio = large_jump_count / total_updates
        assert jump_ratio < 0.1, f"Large jump ratio was {jump_ratio:.2%}, expected < 10%"

    def test_mixed_word_and_chunk_updates(self, number_test_script, number_test_transcript):
        """Verify tracking works with mixed update patterns (some words, some chunks).

        This test adds 1-4 words at a time. For small chunks, jumps should be small.
        Larger jumps indicate validation corrections which should be rare.
        """
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)

        last_position = 0
        large_jumps = []

        # Combine lines into one big list of words
        all_words = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text = ""
        word_idx = 0

        while word_idx < len(all_words):
            # Pick between 1 and 4 words to add using deterministic pattern
            pattern = [1, 3, 2, 4]
            chunk_size = pattern[word_idx % len(pattern)]
            actual_chunk = 0

            # Add chunk_size words
            for _ in range(chunk_size):
                if word_idx >= len(all_words):
                    break
                if cumulative_text:
                    cumulative_text += " " + all_words[word_idx]
                else:
                    cumulative_text = all_words[word_idx]
                word_idx += 1
                actual_chunk += 1

            pos = tracker.update(cumulative_text)
            current_position = pos.speakable_index

            jump = abs(current_position - last_position)

            # For 1-4 word chunks, max reasonable jump is ~8 (2x chunk + margin)
            # Larger jumps indicate validation corrections
            if jump > 8:
                large_jumps.append((jump, actual_chunk))

            last_position = current_position

        # Most updates should have small jumps
        # Allow a few large jumps for validation corrections
        assert len(large_jumps) <= 5, \
            f"Too many large jumps (>8): {len(large_jumps)} - {large_jumps[:5]}"

        # Should reach near the end
        final_progress = tracker.progress
        assert final_progress > 0.8, f"Final progress was {final_progress:.2%}, expected > 80%"

    def test_position_never_exceeds_script_length(self, number_test_script, number_test_transcript):
        """Verify position never goes beyond the script length."""
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)
        script_length = len(tracker.words)

        all_words = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text = ""
        for word in all_words:
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            pos = tracker.update(cumulative_text)

            assert pos.speakable_index <= script_length, \
                f"Position {pos.speakable_index} exceeded script length {script_length}"

    def test_consistent_position_on_repeated_updates(self, number_test_script, number_test_transcript):
        """Verify that updating with the same text doesn't change position."""
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)

        # Build up some context first
        first_few_lines = " ".join(number_test_transcript[:5])

        pos1 = tracker.update(first_few_lines)
        pos2 = tracker.update(first_few_lines)  # Same text
        pos3 = tracker.update(first_few_lines)  # Same text again

        # Position should not change when text doesn't change
        assert pos1.speakable_index == pos2.speakable_index == pos3.speakable_index, \
            f"Position changed on repeated updates: {pos1.speakable_index}, {pos2.speakable_index}, {pos3.speakable_index}"

    def test_steady_progress_through_script(self, number_test_script, number_test_transcript):
        """Verify steady forward progress through the script."""
        from src.autocue.tracker import ScriptTracker

        tracker = ScriptTracker(number_test_script)

        all_words = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text = ""
        progress_samples = []

        # Sample progress at regular intervals
        sample_interval = len(all_words) // 10  # 10 samples

        for i, word in enumerate(all_words):
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            tracker.update(cumulative_text)

            if i > 0 and i % sample_interval == 0:
                progress_samples.append(tracker.progress)

        # Progress should generally increase (allow some small decreases)
        decreases = 0
        for i in range(1, len(progress_samples)):
            if progress_samples[i] < progress_samples[i-1]:
                decreases += 1

        # Should have mostly increasing progress
        assert decreases <= 2, f"Progress decreased {decreases} times, expected <= 2"

        # Progress samples should span a good range
        if len(progress_samples) >= 2:
            progress_range = progress_samples[-1] - progress_samples[0]
            assert progress_range > 0.5, f"Progress range was only {progress_range:.2%}, expected > 50%"
