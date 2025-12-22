# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""Tests for the debug_transcript module."""

import io
import tempfile
from pathlib import Path

from autocue.debug_transcript import (
    TrackingEvent,
    load_script,
    load_transcript,
    replay_transcript,
    replay_transcript_word_by_word,
)


class TestLoadTranscript:
    """Tests for loading transcript files."""

    def test_load_transcript_filters_metadata(self) -> None:
        """Verify metadata lines starting with === are filtered out."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("=== Transcript started at 2025-12-21T00:00:00 ===\n")
            f.write("\n")
            f.write("hello world\n")
            f.write("this is a test\n")
            f.write("\n")
            f.write("=== Transcript ended at 2025-12-21T00:05:00 ===\n")
            f.flush()
            path: Path = Path(f.name)

        lines: list[str] = load_transcript(path)
        assert len(lines) == 2
        assert lines[0] == "hello world"
        assert lines[1] == "this is a test"

    def test_load_transcript_empty_lines_filtered(self) -> None:
        """Verify empty lines are filtered out."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("first line\n")
            f.write("\n")
            f.write("\n")
            f.write("second line\n")
            f.flush()
            path: Path = Path(f.name)

        lines: list[str] = load_transcript(path)
        assert len(lines) == 2
        assert lines[0] == "first line"
        assert lines[1] == "second line"


class TestLoadScript:
    """Tests for loading script files."""

    def test_load_script_returns_content(self) -> None:
        """Verify script content is returned correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Title\n\nThis is the script content.\n")
            f.flush()
            path: Path = Path(f.name)

        content: str = load_script(path)
        assert "# Title" in content
        assert "This is the script content." in content


class TestReplayTranscript:
    """Tests for the replay_transcript function."""

    def test_replay_produces_events(self) -> None:
        """Verify replay produces tracking events."""
        script_text: str = "hello world this is a test script"
        transcript_lines: list[str] = ["hello world", "this is a test"]

        output: io.StringIO = io.StringIO()
        events: list[TrackingEvent] = replay_transcript(
            transcript_lines, script_text, output)

        assert len(events) == 2
        assert all(isinstance(e, TrackingEvent) for e in events)

    def test_replay_tracks_positions(self) -> None:
        """Verify positions advance through the script."""
        script_text: str = "one two three four five six seven"
        transcript_lines: list[str] = ["one two three", "four five six"]

        output: io.StringIO = io.StringIO()
        events: list[TrackingEvent] = replay_transcript(
            transcript_lines, script_text, output)

        # Positions should increase
        assert events[0].script_index < events[1].script_index

    def test_replay_output_contains_header(self) -> None:
        """Verify output contains header information."""
        script_text: str = "hello world"
        transcript_lines: list[str] = ["hello"]

        output: io.StringIO = io.StringIO()
        replay_transcript(transcript_lines, script_text, output)

        output_text: str = output.getvalue()
        assert "TRANSCRIPT DEBUG LOG" in output_text
        assert "SCRIPT WORDS" in output_text
        assert "TRACKING LOG" in output_text
        assert "SUMMARY" in output_text


class TestReplayTranscriptWordByWord:
    """Tests for word-by-word replay mode."""

    def test_word_by_word_produces_more_events(self) -> None:
        """Verify word-by-word mode produces an event per word."""
        script_text: str = "one two three four five"
        transcript_lines: list[str] = ["one two three"]

        output: io.StringIO = io.StringIO()
        events: list[TrackingEvent] = replay_transcript_word_by_word(
            transcript_lines, script_text, output)

        # Should have 3 events (one per word in transcript)
        assert len(events) == 3
        assert events[0].transcript_word == "one"
        assert events[1].transcript_word == "two"
        assert events[2].transcript_word == "three"

    def test_word_by_word_tracks_matches(self) -> None:
        """Verify word-by-word mode tracks matching words."""
        script_text: str = "hello world test"
        transcript_lines: list[str] = ["hello world"]

        output: io.StringIO = io.StringIO()
        events: list[TrackingEvent] = replay_transcript_word_by_word(
            transcript_lines, script_text, output)

        # First word should advance position - we now show the NEW position
        # (where we are after advancing), not where the match happened
        assert events[0].event_type == "advance"
        # New position after 'hello' matched
        assert events[0].script_index == 1
        assert events[0].script_word == "world"  # Word at new position

    def test_word_by_word_verbose_output(self) -> None:
        """Verify verbose mode includes match information."""
        script_text: str = "hello world"
        transcript_lines: list[str] = ["hello world"]

        output: io.StringIO = io.StringIO()
        replay_transcript_word_by_word(
            transcript_lines, script_text, output, verbose=True)

        output_text: str = output.getvalue()
        assert "hello" in output_text
        assert "world" in output_text


class TestTrackingEventTypes:
    """Tests for different tracking event types."""

    def test_detects_forward_progress(self) -> None:
        """Verify forward progress is tracked."""
        script_text: str = "the quick brown fox jumps over the lazy dog"
        transcript_lines: list[str] = ["the quick brown", "fox jumps over"]

        output: io.StringIO = io.StringIO()
        events: list[TrackingEvent] = replay_transcript(
            transcript_lines, script_text, output)

        # Should have advancing positions
        assert events[1].script_index > events[0].script_index
