# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Debug tool for replaying a transcript through the tracker.

This CLI tool takes a transcript file and a script file, simulates
the transcription process, and outputs detailed tracking information
to help debug tracking issues.
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, TextIO

from .tracker import ScriptTracker

EventType = Literal["BACKTRACK", "FORWARD_JUMP",
                    "advance", "no_advance", "no_change", "regress"]


@dataclass
class TrackingEvent:
    """A single tracking event during transcript replay."""
    transcript_line: int
    transcript_word: str
    script_index: int
    script_word: str
    event_type: EventType
    details: str = ""


def load_transcript(path: Path) -> list[str]:
    """Load transcript file and extract transcript lines.

    Filters out metadata lines (starting with '===').
    Returns list of transcript text lines.
    """
    lines: list[str] = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            stripped_line: str = line.strip()
            # Skip metadata lines and empty lines
            if stripped_line.startswith('===') or not stripped_line:
                continue
            lines.append(stripped_line)
    return lines


def load_script(path: Path) -> str:
    """Load script file content."""
    with open(path, encoding='utf-8') as f:
        return f.read()


def replay_transcript(
    transcript_lines: list[str],
    script_text: str,
    output: TextIO,
    verbose: bool = False
) -> list[TrackingEvent]:
    """Replay transcript through tracker and log events.

    Args:
        transcript_lines: Lines of transcript text
        script_text: The script content
        output: File handle to write log output
        verbose: If True, log every word. If False, only log jumps/backtracks.

    Returns:
        List of all tracking events
    """
    tracker: ScriptTracker = ScriptTracker(script_text)
    events: list[TrackingEvent] = []

    # Write header
    output.write("=" * 80 + "\n")
    output.write("TRANSCRIPT DEBUG LOG\n")
    output.write(f"Generated: {datetime.now().isoformat()}\n")
    output.write(f"Script words: {len(tracker.words)}\n")
    output.write(f"Transcript lines: {len(transcript_lines)}\n")
    output.write("=" * 80 + "\n\n")

    # Write script words reference
    output.write("SCRIPT WORDS (speakable):\n")
    output.write("-" * 40 + "\n")
    for i, word in enumerate(tracker.words):
        output.write(f"  [{i:4d}] {word}\n")
    output.write("\n" + "=" * 80 + "\n\n")

    output.write("TRACKING LOG:\n")
    output.write("-" * 40 + "\n")

    cumulative_transcript: str = ""

    for line_num, line in enumerate(transcript_lines, start=1):
        # Simulate cumulative transcript (as Vosk does - each final result
        # is a complete utterance, but we simulate word-by-word buildup)

        line_display: str = f"--- Line {line_num}: \"{line[:60]}"
        line_display += '...' if len(line) > 60 else ''
        line_display += "\" ---"
        output.write(f"\n{line_display}\n")

        # Process the full line as a final result (is_partial=False)
        # This simulates how Vosk delivers final results
        cumulative_transcript = line

        position_before: int = tracker.optimistic_position

        # Update tracker
        result = tracker.update(cumulative_transcript, is_partial=False)

        position_after: int = result.speakable_index

        # Detect event type
        event_type: EventType
        if position_after < position_before:
            event_type = "BACKTRACK"
        elif position_after > position_before + 5:
            event_type = "FORWARD_JUMP"
        elif position_after > position_before:
            event_type = "advance"
        elif position_after == position_before:
            event_type = "no_change"
        else:
            event_type = "regress"

        # Get script word at current position
        script_word: str = (
            tracker.words[position_after]
            if position_after < len(tracker.words)
            else "<END>"
        )

        # Log the tracking result
        details: str = f"pos: {position_before} -> {position_after}"

        if event_type in ("BACKTRACK", "FORWARD_JUMP") or verbose:
            if event_type == "BACKTRACK":
                output.write("  *** BACKTRACK DETECTED ***\n")
                output.write(
                    f"      Position: {position_before} -> {position_after}\n"
                )
                output.write(
                    f"      Script word at new position: \"{script_word}\"\n"
                )
            elif event_type == "FORWARD_JUMP":
                output.write("  *** FORWARD JUMP DETECTED ***\n")
                output.write(
                    f"      Position: {position_before} -> {position_after}\n"
                )
                output.write(
                    f"      Script word at new position: \"{script_word}\"\n"
                )
            else:
                output.write(
                    f"  [{position_after:4d}] \"{script_word}\" ({event_type})\n")

        # Record event
        event: TrackingEvent = TrackingEvent(
            transcript_line=line_num,
            transcript_word=line,
            script_index=position_after,
            script_word=script_word,
            event_type=event_type,
            details=details
        )
        events.append(event)

        # Trigger validation if needed (simulate main loop behavior)
        if tracker.allow_jump_detection:
            validated_pos: int
            was_backtrack: bool
            validated_pos, was_backtrack = tracker.detect_jump(
                cumulative_transcript)
            if was_backtrack or validated_pos != position_after:
                output.write(
                    f"  [VALIDATION] corrected: {position_after} -> {validated_pos}")
                if was_backtrack:
                    output.write(" (BACKTRACK)")
                output.write("\n")

    # Write summary
    output.write("\n" + "=" * 80 + "\n")
    output.write("SUMMARY:\n")
    output.write("-" * 40 + "\n")

    backtracks: list[TrackingEvent] = [
        e for e in events if e.event_type == "BACKTRACK"]
    forward_jumps: list[TrackingEvent] = [
        e for e in events if e.event_type == "FORWARD_JUMP"]
    advances: list[TrackingEvent] = [
        e for e in events if e.event_type == "advance"]

    output.write(f"Total lines processed: {len(transcript_lines)}\n")
    output.write(
        f"Final position: {tracker.optimistic_position} / {len(tracker.words)}\n")
    output.write(f"Advances: {len(advances)}\n")
    output.write(f"Backtracks: {len(backtracks)}\n")
    output.write(f"Forward jumps: {len(forward_jumps)}\n")

    if backtracks:
        output.write("\nBacktrack events:\n")
        for e in backtracks:
            output.write(
                f"  Line {e.transcript_line}: -> position {e.script_index} "
                f"\"{e.script_word}\"\n"
            )

    if forward_jumps:
        output.write("\nForward jump events:\n")
        for e in forward_jumps:
            output.write(
                f"  Line {e.transcript_line}: -> position {e.script_index} "
                f"\"{e.script_word}\"\n"
            )

    return events


def replay_transcript_word_by_word(
    transcript_lines: list[str],
    script_text: str,
    output: TextIO,
    verbose: bool = False
) -> list[TrackingEvent]:
    """Replay transcript word-by-word (simulating partial results).

    This mode simulates how Vosk delivers partial results word by word,
    which gives more granular tracking information.

    Args:
        transcript_lines: Lines of transcript text
        script_text: The script content
        output: File handle to write log output
        verbose: If True, log every word. If False, only log jumps/backtracks.

    Returns:
        List of all tracking events
    """
    tracker: ScriptTracker = ScriptTracker(script_text)
    events: list[TrackingEvent] = []

    # Write header
    output.write("=" * 80 + "\n")
    output.write("TRANSCRIPT DEBUG LOG (WORD-BY-WORD MODE)\n")
    output.write(f"Generated: {datetime.now().isoformat()}\n")
    output.write(f"Script words: {len(tracker.words)}\n")
    output.write(f"Transcript lines: {len(transcript_lines)}\n")
    output.write("=" * 80 + "\n\n")

    # Write script words reference
    output.write("SCRIPT WORDS (speakable):\n")
    output.write("-" * 40 + "\n")
    for i, word in enumerate(tracker.words):
        output.write(f"  [{i:4d}] {word}\n")
    output.write("\n" + "=" * 80 + "\n\n")

    output.write("TRACKING LOG:\n")
    output.write("-" * 40 + "\n")

    word_count: int = 0

    for line_num, line in enumerate(transcript_lines, start=1):
        words: list[str] = line.split()
        if not words:
            continue

        output.write(f"\n--- Line {line_num} ---\n")

        # Build up transcript word by word (simulating partial results)
        partial_transcript: str = ""

        for word_idx, word in enumerate(words):
            word_count += 1

            # Build cumulative partial transcript
            partial_transcript = " ".join(words[:word_idx + 1])

            position_before: int = tracker.optimistic_position

            # Update with partial result
            is_final: bool = word_idx == len(words) - 1
            result = tracker.update(
                partial_transcript, is_partial=not is_final)

            position_after: int = result.speakable_index
            is_backtrack: bool = result.is_jump

            # Detect event type
            # NOTE: "advance" means position moved forward, "no_advance" means position stayed same
            # This does NOT necessarily mean the transcript word matched the script word shown
            event_type: EventType
            if is_backtrack:
                event_type = "BACKTRACK"
            elif position_after > position_before + 5:
                event_type = "FORWARD_JUMP"
            elif position_after > position_before:
                event_type = "advance"
            elif position_after == position_before:
                event_type = "no_advance"
            else:
                event_type = "regress"

            # Get script words for logging
            # For advances: show position_after and the word there
            # For no_advance: show position_before and the word there
            display_pos: int
            script_word: str
            prev_script_word: str | None
            if event_type == "advance":
                # Show the new position we advanced TO
                display_pos = position_after
                script_word = (
                    tracker.words[display_pos]
                    if display_pos < len(tracker.words) else "<END>"
                )
                # Also get the word we advanced FROM for context
                prev_script_word = (
                    tracker.words[position_before]
                    if position_before < len(tracker.words) else "<END>"
                )
            else:
                # Show current position (where we're stuck)
                display_pos = position_before
                script_word = (
                    tracker.words[display_pos]
                    if display_pos < len(tracker.words) else "<END>"
                )
                prev_script_word = None

            # Log the tracking result
            details: str = f"pos: {position_before} -> {position_after}"

            if event_type in ("BACKTRACK", "FORWARD_JUMP") or verbose:
                if event_type == "BACKTRACK":
                    output.write(f"  *** BACKTRACK at \"{word}\" ***\n")
                    output.write(
                        f"      Position: {position_before} -> "
                        f"{position_after}\n"
                    )
                    script_word_after: str = (
                        tracker.words[position_after]
                        if position_after < len(tracker.words) else "<END>"
                    )
                    output.write(
                        f"      Script word at new position: "
                        f"\"{script_word_after}\"\n"
                    )
                elif event_type == "FORWARD_JUMP":
                    output.write(f"  *** FORWARD JUMP at \"{word}\" ***\n")
                    output.write(
                        f"      Position: {position_before} -> "
                        f"{position_after}\n"
                    )
                    script_word_after: str = (
                        tracker.words[position_after]
                        if position_after < len(tracker.words) else "<END>"
                    )
                    output.write(
                        f"      Script word at new position: "
                        f"\"{script_word_after}\"\n"
                    )
                elif event_type == "advance":
                    # Show: position advanced, transcript word, what we passed
                    output.write(
                        f"  * [{display_pos:4d}] \"{word}\" "
                        f"(advanced past \"{prev_script_word}\")\n"
                    )
                else:
                    # no_advance or regress - show where we're stuck
                    output.write(
                        f"    [{display_pos:4d}] \"{word}\" -> "
                        f"\"{script_word}\" ({event_type})\n"
                    )

            # Record event
            event: TrackingEvent = TrackingEvent(
                transcript_line=line_num,
                transcript_word=word,
                script_index=display_pos,
                script_word=script_word,
                event_type=event_type,
                details=details
            )
            events.append(event)

            # Trigger validation if needed
            if tracker.allow_jump_detection:
                validated_pos: int
                was_backtrack: bool
                validated_pos, was_backtrack = (
                    tracker.detect_jump(partial_transcript)
                )
                if was_backtrack or validated_pos != position_after:
                    output.write(
                        f"      [VALIDATION] corrected: {position_after} -> "
                        f"{validated_pos}"
                    )
                    if was_backtrack:
                        output.write(" (BACKTRACK)")
                    output.write("\n")

    # Write summary
    output.write("\n" + "=" * 80 + "\n")
    output.write("SUMMARY:\n")
    output.write("-" * 40 + "\n")

    backtracks: list[TrackingEvent] = [
        e for e in events if e.event_type == "BACKTRACK"]
    forward_jumps: list[TrackingEvent] = [
        e for e in events if e.event_type == "FORWARD_JUMP"]
    advances: list[TrackingEvent] = [
        e for e in events if e.event_type == "advance"]
    no_advances: list[TrackingEvent] = [
        e for e in events if e.event_type == "no_advance"]

    output.write(f"Total words processed: {word_count}\n")
    output.write(
        f"Final position: {tracker.optimistic_position} / {len(tracker.words)}\n")
    output.write(f"Advances: {len(advances)}\n")
    output.write(f"No advances: {len(no_advances)}\n")
    output.write(f"Backtracks: {len(backtracks)}\n")
    output.write(f"Forward jumps: {len(forward_jumps)}\n")

    if backtracks:
        output.write("\nBacktrack events:\n")
        for e in backtracks:
            output.write(
                f"  \"{e.transcript_word}\" -> position {e.script_index} "
                f"\"{e.script_word}\"\n"
            )

    if forward_jumps:
        output.write("\nForward jump events:\n")
        for e in forward_jumps:
            output.write(
                f"  \"{e.transcript_word}\" -> position {e.script_index} "
                f"\"{e.script_word}\"\n"
            )

    return events


def main() -> None:
    """CLI entry point for debug transcript tool."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Debug transcript tracking by replaying a transcript through the tracker"
    )

    parser.add_argument(
        "transcript",
        type=Path,
        help="Path to transcript file"
    )

    parser.add_argument(
        "script",
        type=Path,
        help="Path to script file"
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output log file path (default: stdout)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Log every word, not just jumps/backtracks"
    )

    parser.add_argument(
        "-w", "--word-by-word",
        action="store_true",
        help="Process transcript word-by-word (simulates partial results)"
    )

    args: argparse.Namespace = parser.parse_args()

    # Validate inputs
    if not args.transcript.exists():
        print(
            f"Error: Transcript file not found: {args.transcript}", file=sys.stderr)
        sys.exit(1)

    if not args.script.exists():
        print(f"Error: Script file not found: {args.script}", file=sys.stderr)
        sys.exit(1)

    # Load files
    try:
        transcript_lines: list[str] = load_transcript(args.transcript)
        script_text: str = load_script(args.script)
    except OSError as e:
        print(f"Error loading files: {e}", file=sys.stderr)
        sys.exit(1)

    if not transcript_lines:
        print("Error: No transcript lines found", file=sys.stderr)
        sys.exit(1)

    # Run replay
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            if args.word_by_word:
                replay_transcript_word_by_word(
                    transcript_lines, script_text, f, args.verbose
                )
            else:
                replay_transcript(
                    transcript_lines, script_text, f, args.verbose
                )
        print(f"Debug log written to: {args.output}")
    else:
        if args.word_by_word:
            replay_transcript_word_by_word(
                transcript_lines, script_text, sys.stdout, args.verbose
            )
        else:
            replay_transcript(
                transcript_lines, script_text, sys.stdout, args.verbose
            )


if __name__ == "__main__":
    main()
