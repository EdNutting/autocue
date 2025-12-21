"""Tests for verifying the tracking system follows transcripts smoothly.

These tests use real transcript data to verify that the tracker:
1. Follows the script accurately when given transcript piece by piece
2. Does not jump around unexpectedly
3. Does not backtrack or forward jump excessively
4. Handles differences between transcription and script gracefully
"""

from pathlib import Path

import pytest

from src.autocue.tracker import ScriptPosition, ScriptTracker


class TestTranscriptTracking:
    """Integration tests for tracking with real transcripts."""

    @pytest.fixture
    def number_test_script(self) -> str:
        """Load the number test script."""
        script_path: Path = Path(__file__).parent.parent.parent / \
            "samples" / "number_test_script.md"
        return script_path.read_text()

    @pytest.fixture
    def number_test_transcript(self) -> list[str]:
        """Load and parse the number test transcript, excluding start/end markers."""
        transcript_path: Path = (
            Path(__file__).parent.parent.parent / "transcripts" /
            "transcript_20251221_000011.txt"
        )
        lines: list[str] = transcript_path.read_text().strip().split("\n")

        # Filter out the "Transcript started" and "Transcript ended" lines
        content_lines: list[str] = []
        for line in lines:
            line = line.strip()
            if line.startswith("===") or not line:
                continue
            content_lines.append(line)

        return content_lines

    def test_transcript_loads_correctly(self, number_test_transcript: list[str]) -> None:
        """Verify transcript is loaded and parsed correctly."""
        assert len(number_test_transcript) > 0
        # First content line should be about "number expansion test"
        assert "number" in number_test_transcript[0].lower()

    def test_script_loads_correctly(self, number_test_script: str) -> None:
        """Verify script is loaded correctly."""
        assert len(number_test_script) > 0
        assert "Number Expansion Test Script" in number_test_script

    def test_smooth_tracking_word_by_word(
        self,
        number_test_script: str,
        number_test_transcript: list[str]
    ) -> None:
        """Verify tracking advances smoothly when feeding words one at a time.

        The tracking system should handle number format differences between
        transcription and script (e.g., "one hundred" vs "100") and advance
        smoothly through the script.
        """
        tracker: ScriptTracker = ScriptTracker(number_test_script)

        # Build cumulative transcript word by word
        all_words: list[str] = []
        for line in number_test_transcript:
            words: list[str] = line.split()
            all_words.extend(words)

        max_jump: int = 0
        last_position: int = 0
        position_history: list[int] = [0]

        # Feed every word to simulate word-by-word updates
        cumulative_text: str = ""
        for word in all_words:
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            # Update with cumulative text (tracker compares with last_transcription)
            pos: ScriptPosition = tracker.update(cumulative_text)
            current_position: int = pos.speakable_index

            # Calculate jump size
            jump: int = current_position - last_position
            if abs(jump) > max_jump:
                max_jump = abs(jump)

            position_history.append(current_position)
            last_position = current_position

        # The maximum jump should be small (1-2 words typically, maybe 3 with skipping)
        # We allow up to 5 to account for skip-ahead matching
        assert max_jump <= 5, f"Maximum jump was {max_jump}, expected <= 5"

        # Position should have advanced significantly through the script
        final_progress: float = tracker.progress
        assert final_progress > 0.8, f"Final progress was {final_progress:.2%}, expected > 80%"

    def test_smooth_tracking_chunk_by_chunk(
        self,
        number_test_script: str,
        number_test_transcript: list[str]
    ) -> None:
        """Verify tracking advances smoothly when feeding transcript line by line (chunks).

        For chunk updates, jumps should be proportional to the number of words in the chunk.
        We verify that no jump exceeds the chunk size by more than a small margin.
        """
        tracker: ScriptTracker = ScriptTracker(number_test_script)

        last_position: int = 0
        disproportionate_jumps: list[tuple[int, int, str]] = []

        # Feed transcript line by line (simulating chunks of speech)
        cumulative_text: str = ""
        for line in number_test_transcript:
            if cumulative_text:
                cumulative_text += " " + line
            else:
                cumulative_text = line

            chunk_word_count: int = len(line.split())
            pos: ScriptPosition = tracker.update(cumulative_text)
            current_position: int = pos.speakable_index

            # Calculate jump size
            jump: int = current_position - last_position

            # For chunk updates, jump should be approximately equal to chunk size
            # Allow some tolerance for skipped words or minor mismatches
            # A jump should not exceed 1.5x the chunk size (50% tolerance)
            max_reasonable_jump: int = max(5, int(chunk_word_count * 1.5))
            if jump > max_reasonable_jump:
                disproportionate_jumps.append(
                    (jump, chunk_word_count, line[:40]))

            last_position = current_position

        # There should be very few disproportionate jumps (validation corrections)
        assert len(disproportionate_jumps) <= 2, \
            f"Too many disproportionate jumps: {disproportionate_jumps}"

        # Position should have advanced significantly
        final_progress: float = tracker.progress
        assert final_progress > 0.8, f"Final progress was {final_progress:.2%}, expected > 80%"

    def test_no_backtracking(
        self,
        number_test_script: str,
        number_test_transcript: list[str]
    ) -> None:
        """Verify that tracking never goes backward unexpectedly."""
        tracker: ScriptTracker = ScriptTracker(number_test_script)

        position_before: int = 0
        backtrack_count: int = 0
        largest_backtrack: int = 0

        # Feed transcript word by word
        all_words: list[str] = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text: str = ""
        for word in all_words:
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            pos: ScriptPosition = tracker.update(cumulative_text)
            current_position: int = pos.speakable_index

            if current_position < position_before:
                backtrack_amount: int = position_before - current_position
                backtrack_count += 1
                if backtrack_amount > largest_backtrack:
                    largest_backtrack = backtrack_amount
            else:
                position_before = current_position

        # There should be no backtracks (or very few, very small ones)
        assert largest_backtrack <= 2, \
            f"Largest backtrack was {largest_backtrack} words, expected <= 2"
        # Allow a few small backtracks due to speech recognition differences
        assert backtrack_count <= 3, f"Backtrack count was {backtrack_count}, expected <= 3"

    def test_no_forward_jumps(
        self,
        number_test_script: str,
        number_test_transcript: list[str]
    ) -> None:
        """Verify that tracking never jumps forward unexpectedly."""
        tracker: ScriptTracker = ScriptTracker(number_test_script)

        large_jump_count: int = 0
        largest_forward_jump: int = 0

        # Feed transcript word by word
        all_words: list[str] = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text: str = ""
        last_position: int = 0

        for word in all_words:
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            pos: ScriptPosition = tracker.update(cumulative_text)
            current_position: int = pos.speakable_index

            forward_jump: int = current_position - last_position

            # Count jumps larger than 2 (normal matching might skip 1-2 words)
            if forward_jump > 2:
                large_jump_count += 1
                if forward_jump > largest_forward_jump:
                    largest_forward_jump = forward_jump

            last_position = current_position

        # Large forward jumps should be rare
        # We allow some due to word skipping (speaker skips a word)
        assert largest_forward_jump <= 5, \
            f"Largest forward jump was {largest_forward_jump} words, expected <= 5"
        # Most updates should advance by 0-2 words
        total_updates: int = len(all_words)
        jump_ratio: float = large_jump_count / total_updates
        assert jump_ratio < 0.1, f"Large jump ratio was {jump_ratio:.2%}, expected < 10%"

    def test_mixed_word_and_chunk_updates(
        self,
        number_test_script: str,
        number_test_transcript: list[str]
    ) -> None:
        """Verify tracking works with mixed update patterns (some words, some chunks).

        This test adds 1-4 words at a time. For small chunks, jumps should be small.
        Larger jumps indicate validation corrections which should be rare.
        """
        tracker: ScriptTracker = ScriptTracker(number_test_script)

        last_position: int = 0
        large_jumps: list[tuple[int, int]] = []

        # Combine lines into one big list of words
        all_words: list[str] = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text: str = ""
        word_idx: int = 0

        while word_idx < len(all_words):
            # Pick between 1 and 4 words to add using deterministic pattern
            pattern: list[int] = [1, 3, 2, 4]
            chunk_size: int = pattern[word_idx % len(pattern)]
            actual_chunk: int = 0

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

            pos: ScriptPosition = tracker.update(cumulative_text)
            current_position: int = pos.speakable_index

            jump: int = abs(current_position - last_position)

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
        final_progress: float = tracker.progress
        assert final_progress > 0.8, f"Final progress was {final_progress:.2%}, expected > 80%"

    def test_position_never_exceeds_script_length(
        self, number_test_script: str, number_test_transcript: list[str]
    ) -> None:
        """Verify position never goes beyond the script length."""
        tracker: ScriptTracker = ScriptTracker(number_test_script)
        script_length: int = len(tracker.words)

        all_words: list[str] = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text: str = ""
        for word in all_words:
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            pos: ScriptPosition = tracker.update(cumulative_text)

            assert pos.speakable_index <= script_length, \
                f"Position {pos.speakable_index} exceeded script length {script_length}"

    def test_consistent_position_on_repeated_updates(
        self, number_test_script: str, number_test_transcript: list[str]
    ) -> None:
        """Verify that updating with the same text doesn't change position."""
        tracker: ScriptTracker = ScriptTracker(number_test_script)

        # Build up some context first
        first_few_lines: str = " ".join(number_test_transcript[:5])

        pos1: ScriptPosition = tracker.update(first_few_lines)
        pos2: ScriptPosition = tracker.update(first_few_lines)  # Same text
        pos3: ScriptPosition = tracker.update(
            first_few_lines)  # Same text again

        # Position should not change when text doesn't change
        assert pos1.speakable_index == pos2.speakable_index == pos3.speakable_index, \
            (f"Position changed on repeated updates: "
             f"{pos1.speakable_index}, {pos2.speakable_index}, {pos3.speakable_index}")

    def test_steady_progress_through_script(
        self,
        number_test_script: str,
        number_test_transcript: list[str]
    ) -> None:
        """Verify steady forward progress through the script."""
        tracker: ScriptTracker = ScriptTracker(number_test_script)

        all_words: list[str] = []
        for line in number_test_transcript:
            all_words.extend(line.split())

        cumulative_text: str = ""
        progress_samples: list[float] = []

        # Sample progress at regular intervals
        sample_interval: int = len(all_words) // 10  # 10 samples

        for i, word in enumerate(all_words):
            if cumulative_text:
                cumulative_text += " " + word
            else:
                cumulative_text = word

            tracker.update(cumulative_text)

            if i > 0 and i % sample_interval == 0:
                progress_samples.append(tracker.progress)

        # Progress should generally increase (allow some small decreases)
        decreases: int = 0
        for i in range(1, len(progress_samples)):
            if progress_samples[i] < progress_samples[i-1]:
                decreases += 1

        # Should have mostly increasing progress
        assert decreases <= 2, f"Progress decreased {decreases} times, expected <= 2"

        # Progress samples should span a good range
        if len(progress_samples) >= 2:
            progress_range: float = progress_samples[-1] - progress_samples[0]
            assert progress_range > 0.5, \
                f"Progress range was only {progress_range:.2%}, expected > 50%"
