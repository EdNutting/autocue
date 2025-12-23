#!/usr/bin/env python3
# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Example script demonstrating how to profile the tracking algorithm.

This shows how to use the profiling infrastructure to identify performance
bottlenecks in real-world tracking scenarios.
"""

from pathlib import Path

from autocue.profiling import enable_profiling, get_profiler, profile_cprofile
from autocue.tracker import ScriptTracker


def main():
    """Run a profiled tracking session."""
    # Load a sample script
    samples_dir = Path(__file__).parent.parent / "samples"
    script_path = samples_dir / "gettysburg.md"

    if not script_path.exists():
        print(f"Sample script not found: {script_path}")
        print("Using inline script instead")
        script_text = """
# Sample Script

This is a sample script for performance testing.
The quick brown fox jumps over the lazy dog.
She sells sea shells by the sea shore.
Peter Piper picked a peck of pickled peppers.
"""
    else:
        script_text = script_path.read_text(encoding="utf-8")

    print("=" * 80)
    print("TRACKING PERFORMANCE PROFILING")
    print("=" * 80)
    print(f"Script: {script_path if script_path.exists() else 'inline'}")
    print()

    # Enable profiling with percentile tracking
    enable_profiling(keep_all_times=True)

    # Create tracker
    tracker = ScriptTracker(script_text)
    print(f"Script loaded: {len(tracker.words)} words")
    print()

    # Simulate a realistic tracking session
    print("Simulating realistic tracking session...")
    print("- Growing partial transcripts")
    print("- Final updates")
    print("- Some backtracking")
    print()

    # Go through first 100 words (or all if fewer)
    max_words = min(100, len(tracker.words))
    pos = 0

    while pos < max_words:
        # Simulate 5-word utterance
        chunk_size = 5
        chunk_words = tracker.words[pos:pos+chunk_size]

        # Simulate growing partials (like Vosk does)
        for i in range(1, len(chunk_words) + 1):
            partial = " ".join(tracker.words[:pos+i])
            tracker.update(partial, is_partial=True)

        # Final update
        final = " ".join(tracker.words[:pos+len(chunk_words)])
        tracker.update(final, is_partial=False)

        pos += chunk_size

    # Simulate a backtrack (speaker restarts)
    if max_words > 20:
        print("Simulating backtrack to word 20...")
        backtrack_text = " ".join(tracker.words[20:30])
        tracker.update(backtrack_text, is_partial=False)

    print()
    print("=" * 80)
    print("PROFILING RESULTS")
    print("=" * 80)

    # Print performance report
    profiler = get_profiler()
    profiler.print_report(top_n=20, sort_by="total")

    # Save detailed report
    output_dir = Path(__file__).parent.parent / "profiling_results"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "tracking_profile.json"
    profiler.save_report(report_path)
    print(f"Detailed report saved to: {report_path}")
    print()

    # Optional: Run with cProfile for even more detail
    print("=" * 80)
    print("DETAILED cProfile ANALYSIS")
    print("=" * 80)
    print()

    # Reset tracker
    tracker.reset()

    # Run with cProfile
    cprofile_path = output_dir / "tracking_cprofile.prof"
    with profile_cprofile(cprofile_path, top_n=30):
        # Simulate same session
        pos = 0
        while pos < max_words:
            chunk_size = 5
            chunk_words = tracker.words[pos:pos+chunk_size]

            for i in range(1, len(chunk_words) + 1):
                partial = " ".join(tracker.words[:pos+i])
                tracker.update(partial, is_partial=True)

            final = " ".join(tracker.words[:pos+len(chunk_words)])
            tracker.update(final, is_partial=False)

            pos += chunk_size

    print()
    print(f"cProfile stats saved to: {cprofile_path}")
    print(f"Analyze with: python -m pstats {cprofile_path}")
    print()
    print("=" * 80)
    print("PROFILING COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
