# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Performance benchmarking tests for the tracking algorithm.

These tests measure real-world performance of the tracking algorithm
to identify bottlenecks and ensure acceptable latency.
"""

import time
from pathlib import Path

import pytest

from autocue.profiling import (
    enable_profiling,
    get_profiler,
    profile_cprofile,
    reset_profiling,
)
from autocue.tracker import ScriptTracker


class TestTrackingPerformance:
    """Performance benchmarks for the ScriptTracker."""

    @pytest.fixture(autouse=True)
    def setup_profiling(self):
        """Enable profiling for all performance tests."""
        reset_profiling()
        enable_profiling(keep_all_times=True)
        yield
        # Print report after each test
        get_profiler().print_report(top_n=30, sort_by="total")

    @pytest.fixture
    def sample_script(self) -> str:
        """Load a realistic sample script."""
        samples_dir = Path(__file__).parent.parent / "samples"
        script_path = samples_dir / "gettysburg.md"
        if script_path.exists():
            return script_path.read_text(encoding="utf-8")
        # Fallback to inline script if sample doesn't exist
        return """
# Sample Script

This is a sample script for performance testing.
We need enough text to make the tracking realistic.

The quick brown fox jumps over the lazy dog.
She sells sea shells by the sea shore.
Peter Piper picked a peck of pickled peppers.

## More Content

Numbers like 123 and 456 should be expanded properly.
Punctuation like & and / should work correctly too.

The tracking algorithm needs to handle:
- Fuzzy matching for speech recognition errors
- Backtracking when the speaker restarts
- Forward jumps when skipping ahead
- Partial transcripts that update in real-time

## Final Section

This section ensures we have enough content to test
the window-based matching and jump detection algorithms.
"""

    def test_initialization_performance(self, sample_script: str):
        """Benchmark tracker initialization time."""
        iterations = 100
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            tracker = ScriptTracker(sample_script)
            duration = time.perf_counter() - start
            times.append(duration)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        print(f"\nInitialization Performance:")
        print(f"  Iterations: {iterations}")
        print(f"  Average: {avg_time*1000:.2f}ms")
        print(f"  Max: {max_time*1000:.2f}ms")
        print(f"  Script words: {len(tracker.words)}")

        # Initialization should be fast (< 50ms on average)
        assert avg_time < 0.05, f"Initialization too slow: {avg_time*1000:.2f}ms"

    def test_sequential_word_matching_performance(self, sample_script: str):
        """Benchmark sequential word-by-word matching (ideal case)."""
        tracker = ScriptTracker(sample_script)

        # Simulate perfect sequential matching
        words = tracker.words[:100]  # First 100 words
        iterations = 10

        times = []
        for _ in range(iterations):
            tracker.reset()
            start = time.perf_counter()

            # Feed words one by one (simulating perfect speech recognition)
            for word in words:
                tracker.update(word, is_partial=False)

            duration = time.perf_counter() - start
            times.append(duration)

        avg_time = sum(times) / len(times)
        avg_per_word = avg_time / len(words)

        print(f"\nSequential Matching Performance:")
        print(f"  Words: {len(words)}")
        print(f"  Iterations: {iterations}")
        print(f"  Average total: {avg_time*1000:.2f}ms")
        print(f"  Average per word: {avg_per_word*1000:.3f}ms")

        # Each word should be processed quickly (< 2ms per word)
        assert avg_per_word < 0.002, f"Word matching too slow: {avg_per_word*1000:.3f}ms per word"

    def test_partial_update_performance(self, sample_script: str):
        """Benchmark partial transcript updates (real-time scenario)."""
        tracker = ScriptTracker(sample_script)

        # Simulate a growing partial transcript (realistic Vosk behavior)
        test_phrase = " ".join(tracker.words[10:30])  # 20-word phrase
        words = test_phrase.split()

        times = []
        for i in range(1, len(words) + 1):
            partial = " ".join(words[:i])
            start = time.perf_counter()
            tracker.update(partial, is_partial=True)
            duration = time.perf_counter() - start
            times.append(duration)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        print(f"\nPartial Update Performance:")
        print(f"  Updates: {len(times)}")
        print(f"  Average: {avg_time*1000:.3f}ms")
        print(f"  Max: {max_time*1000:.3f}ms")
        print(f"  P95: {sorted(times)[int(len(times)*0.95)]*1000:.3f}ms")

        # Partial updates should be fast (< 5ms average, < 20ms P95)
        # These happen frequently in real-time
        assert avg_time < 0.005, f"Partial updates too slow: {avg_time*1000:.3f}ms"
        assert sorted(times)[int(len(times)*0.95)] < 0.020, "P95 latency too high"

    def test_final_update_performance(self, sample_script: str):
        """Benchmark final transcript updates."""
        tracker = ScriptTracker(sample_script)

        # Simulate final updates with accumulating transcripts
        chunks = []
        for i in range(0, 50, 5):  # 10 chunks of 5 words each
            chunk = " ".join(tracker.words[i:i+5])
            chunks.append(chunk)

        times = []
        accumulated = ""
        for chunk in chunks:
            accumulated += " " + chunk
            start = time.perf_counter()
            tracker.update(accumulated.strip(), is_partial=False)
            duration = time.perf_counter() - start
            times.append(duration)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        print(f"\nFinal Update Performance:")
        print(f"  Updates: {len(times)}")
        print(f"  Average: {avg_time*1000:.3f}ms")
        print(f"  Max: {max_time*1000:.3f}ms")

        # Final updates can be slower but should still be reasonable
        assert avg_time < 0.01, f"Final updates too slow: {avg_time*1000:.3f}ms"

    def test_backtrack_detection_performance(self, sample_script: str):
        """Benchmark backtrack detection performance."""
        tracker = ScriptTracker(sample_script)

        # Advance to middle of script
        midpoint = " ".join(tracker.words[:50])
        tracker.update(midpoint, is_partial=False)

        # Simulate backtracking to earlier position
        backtrack_text = " ".join(tracker.words[20:30])

        times = []
        iterations = 50

        for _ in range(iterations):
            # Reset to midpoint
            tracker.reset()
            tracker.update(midpoint, is_partial=False)

            # Measure backtrack detection
            start = time.perf_counter()
            tracker.update(backtrack_text, is_partial=False)
            duration = time.perf_counter() - start
            times.append(duration)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        print(f"\nBacktrack Detection Performance:")
        print(f"  Iterations: {iterations}")
        print(f"  Average: {avg_time*1000:.3f}ms")
        print(f"  Max: {max_time*1000:.3f}ms")

        # Backtrack detection involves window searching, so can be slower
        # But should still be fast enough for real-time
        assert avg_time < 0.015, f"Backtrack detection too slow: {avg_time*1000:.3f}ms"

    def test_fuzzy_matching_performance(self, sample_script: str):
        """Benchmark fuzzy matching with speech recognition errors."""
        tracker = ScriptTracker(sample_script)

        # Simulate speech recognition errors (slightly wrong words)
        def add_errors(text: str) -> str:
            """Add realistic speech recognition errors."""
            words = text.split()
            # Change every 5th word slightly
            for i in range(0, len(words), 5):
                if len(words[i]) > 3:
                    # Drop a character to simulate error
                    words[i] = words[i][:-1]
            return " ".join(words)

        test_text = " ".join(tracker.words[10:40])
        errorful_text = add_errors(test_text)

        times = []
        iterations = 50

        for _ in range(iterations):
            tracker.reset()
            start = time.perf_counter()
            tracker.update(errorful_text, is_partial=False)
            duration = time.perf_counter() - start
            times.append(duration)

        avg_time = sum(times) / len(times)

        print(f"\nFuzzy Matching Performance:")
        print(f"  Iterations: {iterations}")
        print(f"  Words: {len(errorful_text.split())}")
        print(f"  Average: {avg_time*1000:.3f}ms")

        # Fuzzy matching is more expensive but should still be fast
        assert avg_time < 0.020, f"Fuzzy matching too slow: {avg_time*1000:.3f}ms"

    def test_realistic_session_performance(self, sample_script: str):
        """Benchmark a realistic session with mixed updates."""
        tracker = ScriptTracker(sample_script)

        # Simulate a realistic session:
        # - Growing partial transcripts
        # - Final updates that advance position
        # - Occasional backtracks

        session_times = {
            "partial": [],
            "final": [],
            "total": 0
        }

        start_total = time.perf_counter()

        # Simulate going through first 100 words
        pos = 0
        while pos < min(100, len(tracker.words)):
            # Simulate 5-word utterance
            chunk_size = 5
            chunk_words = tracker.words[pos:pos+chunk_size]

            # Growing partials
            for i in range(1, len(chunk_words) + 1):
                partial = " ".join(tracker.words[:pos+i])
                start = time.perf_counter()
                tracker.update(partial, is_partial=True)
                session_times["partial"].append(time.perf_counter() - start)

            # Final
            final = " ".join(tracker.words[:pos+len(chunk_words)])
            start = time.perf_counter()
            tracker.update(final, is_partial=False)
            session_times["final"].append(time.perf_counter() - start)

            pos += chunk_size

        session_times["total"] = time.perf_counter() - start_total

        print(f"\nRealistic Session Performance:")
        print(f"  Total duration: {session_times['total']*1000:.2f}ms")
        print(f"  Partial updates: {len(session_times['partial'])}")
        print(f"    Avg: {sum(session_times['partial'])/len(session_times['partial'])*1000:.3f}ms")
        print(f"    Max: {max(session_times['partial'])*1000:.3f}ms")
        print(f"  Final updates: {len(session_times['final'])}")
        print(f"    Avg: {sum(session_times['final'])/len(session_times['final'])*1000:.3f}ms")
        print(f"    Max: {max(session_times['final'])*1000:.3f}ms")

        # Overall session should be efficient
        avg_partial = sum(session_times['partial'])/len(session_times['partial'])
        avg_final = sum(session_times['final'])/len(session_times['final'])

        assert avg_partial < 0.005, f"Partial updates too slow in session: {avg_partial*1000:.3f}ms"
        assert avg_final < 0.015, f"Final updates too slow in session: {avg_final*1000:.3f}ms"

    @pytest.mark.slow
    def test_comprehensive_cprofile(self, sample_script: str):
        """Run comprehensive cProfile analysis on tracking algorithm."""
        tracker = ScriptTracker(sample_script)

        # Create output directory
        output_dir = Path(__file__).parent.parent / "profiling_results"
        output_dir.mkdir(exist_ok=True)

        with profile_cprofile(output_dir / "tracking_profile.prof", top_n=50):
            # Simulate realistic usage
            for i in range(0, min(200, len(tracker.words)), 10):
                chunk = " ".join(tracker.words[i:i+10])

                # Partials
                words = chunk.split()
                for j in range(1, len(words) + 1):
                    partial = " ".join(tracker.words[:i+j])
                    tracker.update(partial, is_partial=True)

                # Final
                final = " ".join(tracker.words[:i+len(words)])
                tracker.update(final, is_partial=False)

        print(f"\nDetailed cProfile saved to: {output_dir / 'tracking_profile.prof'}")
        print("Analyze with: python -m pstats profiling_results/tracking_profile.prof")

    def test_save_profiling_report(self, sample_script: str):
        """Save detailed profiling report to JSON."""
        tracker = ScriptTracker(sample_script)

        # Run some operations
        for i in range(0, 50, 5):
            chunk = " ".join(tracker.words[i:i+5])
            tracker.update(chunk, is_partial=False)

        # Save report
        output_dir = Path(__file__).parent.parent / "profiling_results"
        output_dir.mkdir(exist_ok=True)

        profiler = get_profiler()
        report_path = output_dir / "performance_report.json"
        profiler.save_report(report_path)

        print(f"\nPerformance report saved to: {report_path}")
        assert report_path.exists()
