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
from typing import List, Optional, TextIO

from .tracker import ScriptTracker


@dataclass
class TrackingEvent:
    """A single tracking event during transcript replay."""
    transcript_line: int
    transcript_word: str
    script_index: int
    script_word: str
    event_type: str  # "match", "backtrack", "forward_jump", "no_match"
    details: str = ""


def load_transcript(path: Path) -> List[str]:
    """Load transcript file and extract transcript lines.

    Filters out metadata lines (starting with '===').
    Returns list of transcript text lines.
    """
    lines = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip metadata lines and empty lines
            if line.startswith('===') or not line:
                continue
            lines.append(line)
    return lines


def load_script(path: Path) -> str:
    """Load script file content."""
    with open(path, 'r') as f:
        return f.read()


def replay_transcript(
    transcript_lines: List[str],
    script_text: str,
    output: TextIO,
    verbose: bool = False
) -> List[TrackingEvent]:
    """Replay transcript through tracker and log events.

    Args:
        transcript_lines: Lines of transcript text
        script_text: The script content
        output: File handle to write log output
        verbose: If True, log every word. If False, only log jumps/backtracks.

    Returns:
        List of all tracking events
    """
    tracker = ScriptTracker(script_text)
    events: List[TrackingEvent] = []

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

    prev_position = 0
    cumulative_transcript = ""

    for line_num, line in enumerate(transcript_lines, start=1):
        # Simulate cumulative transcript (as Vosk does - each final result
        # is a complete utterance, but we simulate word-by-word buildup)
        words = line.split()

        output.write(f"\n--- Line {line_num}: \"{line[:60]}{'...' if len(line) > 60 else ''}\" ---\n")

        # Process the full line as a final result (is_partial=False)
        # This simulates how Vosk delivers final results
        cumulative_transcript = line

        position_before = tracker.optimistic_position
        high_water_before = tracker.high_water_mark

        # Update tracker
        result = tracker.update(cumulative_transcript, is_partial=False)

        position_after = result.speakable_index
        is_backtrack = result.is_backtrack

        # Detect event type
        if is_backtrack:
            event_type = "BACKTRACK"
        elif position_after > high_water_before + 5:
            event_type = "FORWARD_JUMP"
        elif position_after > position_before:
            event_type = "advance"
        elif position_after == position_before:
            event_type = "no_change"
        else:
            event_type = "regress"

        # Get script word at current position
        script_word = tracker.words[position_after] if position_after < len(tracker.words) else "<END>"

        # Log the tracking result
        details = (
            f"pos: {position_before} -> {position_after} "
            f"(hwm: {high_water_before} -> {tracker.high_water_mark})"
        )

        if event_type in ("BACKTRACK", "FORWARD_JUMP") or verbose:
            if event_type == "BACKTRACK":
                output.write(f"  *** BACKTRACK DETECTED ***\n")
                output.write(f"      Position: {position_before} -> {position_after}\n")
                output.write(f"      High water mark: {high_water_before} -> {tracker.high_water_mark}\n")
                output.write(f"      Script word at new position: \"{script_word}\"\n")
            elif event_type == "FORWARD_JUMP":
                output.write(f"  *** FORWARD JUMP DETECTED ***\n")
                output.write(f"      Position: {position_before} -> {position_after}\n")
                output.write(f"      High water mark: {high_water_before} -> {tracker.high_water_mark}\n")
                output.write(f"      Script word at new position: \"{script_word}\"\n")
            else:
                output.write(f"  [{position_after:4d}] \"{script_word}\" ({event_type})\n")

        # Record event
        event = TrackingEvent(
            transcript_line=line_num,
            transcript_word=line,
            script_index=position_after,
            script_word=script_word,
            event_type=event_type,
            details=details
        )
        events.append(event)

        # Trigger validation if needed (simulate main loop behavior)
        if tracker.needs_validation:
            validated_pos, was_backtrack = tracker.validate_position(cumulative_transcript)
            if was_backtrack or validated_pos != position_after:
                output.write(f"  [VALIDATION] corrected: {position_after} -> {validated_pos}")
                if was_backtrack:
                    output.write(" (BACKTRACK)")
                output.write("\n")

        prev_position = position_after

    # Write summary
    output.write("\n" + "=" * 80 + "\n")
    output.write("SUMMARY:\n")
    output.write("-" * 40 + "\n")

    backtracks = [e for e in events if e.event_type == "BACKTRACK"]
    forward_jumps = [e for e in events if e.event_type == "FORWARD_JUMP"]
    advances = [e for e in events if e.event_type == "advance"]

    output.write(f"Total lines processed: {len(transcript_lines)}\n")
    output.write(f"Final position: {tracker.optimistic_position} / {len(tracker.words)}\n")
    output.write(f"High water mark: {tracker.high_water_mark}\n")
    output.write(f"Advances: {len(advances)}\n")
    output.write(f"Backtracks: {len(backtracks)}\n")
    output.write(f"Forward jumps: {len(forward_jumps)}\n")

    if backtracks:
        output.write("\nBacktrack events:\n")
        for e in backtracks:
            output.write(f"  Line {e.transcript_line}: -> position {e.script_index} \"{e.script_word}\"\n")

    if forward_jumps:
        output.write("\nForward jump events:\n")
        for e in forward_jumps:
            output.write(f"  Line {e.transcript_line}: -> position {e.script_index} \"{e.script_word}\"\n")

    return events


def replay_transcript_word_by_word(
    transcript_lines: List[str],
    script_text: str,
    output: TextIO,
    verbose: bool = False
) -> List[TrackingEvent]:
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
    tracker = ScriptTracker(script_text)
    events: List[TrackingEvent] = []

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

    prev_position = 0
    word_count = 0

    for line_num, line in enumerate(transcript_lines, start=1):
        words = line.split()
        if not words:
            continue

        output.write(f"\n--- Line {line_num} ---\n")

        # Build up transcript word by word (simulating partial results)
        partial_transcript = ""

        for word_idx, word in enumerate(words):
            word_count += 1

            # Build cumulative partial transcript
            partial_transcript = " ".join(words[:word_idx + 1])

            position_before = tracker.optimistic_position
            high_water_before = tracker.high_water_mark

            # Update with partial result
            is_final = (word_idx == len(words) - 1)
            result = tracker.update(partial_transcript, is_partial=not is_final)

            position_after = result.speakable_index
            is_backtrack = result.is_backtrack

            # Detect event type
            # NOTE: "advance" means position moved forward, "no_advance" means position stayed same
            # This does NOT necessarily mean the transcript word matched the script word shown
            if is_backtrack:
                event_type = "BACKTRACK"
            elif position_after > high_water_before + 5:
                event_type = "FORWARD_JUMP"
            elif position_after > position_before:
                event_type = "advance"
            elif position_after == position_before:
                event_type = "no_advance"
            else:
                event_type = "regress"

            # Get script words for logging
            # For advances: show position_after (where we are now) and the word there
            # For no_advance: show position_before (where we're stuck) and the word there
            if event_type == "advance":
                # Show the new position we advanced TO
                display_pos = position_after
                script_word = tracker.words[display_pos] if display_pos < len(tracker.words) else "<END>"
                # Also get the word we advanced FROM for context
                prev_script_word = tracker.words[position_before] if position_before < len(tracker.words) else "<END>"
            else:
                # Show current position (where we're stuck)
                display_pos = position_before
                script_word = tracker.words[display_pos] if display_pos < len(tracker.words) else "<END>"
                prev_script_word = None

            # Log the tracking result
            details = f"pos: {position_before} -> {position_after}"

            if event_type in ("BACKTRACK", "FORWARD_JUMP") or verbose:
                if event_type == "BACKTRACK":
                    output.write(f"  *** BACKTRACK at \"{word}\" ***\n")
                    output.write(
                        f"      Position: {position_before} -> {position_after}\n"
                    )
                    output.write(
                        f"      High water mark: "
                        f"{high_water_before} -> {tracker.high_water_mark}\n"
                    )
                    script_word_after = (
                        tracker.words[position_after]
                        if position_after < len(tracker.words) else "<END>"
                    )
                    output.write(
                        f"      Script word at new position: \"{script_word_after}\"\n"
                    )
                elif event_type == "FORWARD_JUMP":
                    output.write(f"  *** FORWARD JUMP at \"{word}\" ***\n")
                    output.write(
                        f"      Position: {position_before} -> {position_after}\n"
                    )
                    output.write(
                        f"      High water mark: "
                        f"{high_water_before} -> {tracker.high_water_mark}\n"
                    )
                    script_word_after = (
                        tracker.words[position_after]
                        if position_after < len(tracker.words) else "<END>"
                    )
                    output.write(
                        f"      Script word at new position: \"{script_word_after}\"\n"
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
                        f"    [{display_pos:4d}] \"{word}\" -> \"{script_word}\" "
                        f"({event_type})\n"
                    )

            # Record event
            event = TrackingEvent(
                transcript_line=line_num,
                transcript_word=word,
                script_index=display_pos,
                script_word=script_word,
                event_type=event_type,
                details=details
            )
            events.append(event)

            # Trigger validation if needed
            if tracker.needs_validation:
                validated_pos, was_backtrack = tracker.validate_position(partial_transcript)
                if was_backtrack or validated_pos != position_after:
                    output.write(f"      [VALIDATION] corrected: {position_after} -> {validated_pos}")
                    if was_backtrack:
                        output.write(" (BACKTRACK)")
                    output.write("\n")

            prev_position = position_after

    # Write summary
    output.write("\n" + "=" * 80 + "\n")
    output.write("SUMMARY:\n")
    output.write("-" * 40 + "\n")

    backtracks = [e for e in events if e.event_type == "BACKTRACK"]
    forward_jumps = [e for e in events if e.event_type == "FORWARD_JUMP"]
    advances = [e for e in events if e.event_type == "advance"]
    no_advances = [e for e in events if e.event_type == "no_advance"]

    output.write(f"Total words processed: {word_count}\n")
    output.write(f"Final position: {tracker.optimistic_position} / {len(tracker.words)}\n")
    output.write(f"High water mark: {tracker.high_water_mark}\n")
    output.write(f"Advances: {len(advances)}\n")
    output.write(f"No advances: {len(no_advances)}\n")
    output.write(f"Backtracks: {len(backtracks)}\n")
    output.write(f"Forward jumps: {len(forward_jumps)}\n")

    if backtracks:
        output.write("\nBacktrack events:\n")
        for e in backtracks:
            output.write(f"  \"{e.transcript_word}\" -> position {e.script_index} \"{e.script_word}\"\n")

    if forward_jumps:
        output.write("\nForward jump events:\n")
        for e in forward_jumps:
            output.write(f"  \"{e.transcript_word}\" -> position {e.script_index} \"{e.script_word}\"\n")

    return events


def main():
    """CLI entry point for debug transcript tool."""
    parser = argparse.ArgumentParser(
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

    args = parser.parse_args()

    # Validate inputs
    if not args.transcript.exists():
        print(f"Error: Transcript file not found: {args.transcript}", file=sys.stderr)
        sys.exit(1)

    if not args.script.exists():
        print(f"Error: Script file not found: {args.script}", file=sys.stderr)
        sys.exit(1)

    # Load files
    try:
        transcript_lines = load_transcript(args.transcript)
        script_text = load_script(args.script)
    except OSError as e:
        print(f"Error loading files: {e}", file=sys.stderr)
        sys.exit(1)

    if not transcript_lines:
        print("Error: No transcript lines found", file=sys.stderr)
        sys.exit(1)

    # Run replay
    if args.output:
        with open(args.output, 'w') as f:
            if args.word_by_word:
                replay_transcript_word_by_word(transcript_lines, script_text, f, args.verbose)
            else:
                replay_transcript(transcript_lines, script_text, f, args.verbose)
        print(f"Debug log written to: {args.output}")
    else:
        if args.word_by_word:
            replay_transcript_word_by_word(transcript_lines, script_text, sys.stdout, args.verbose)
        else:
            replay_transcript(transcript_lines, script_text, sys.stdout, args.verbose)


if __name__ == "__main__":
    main()
