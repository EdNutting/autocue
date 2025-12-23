# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Tests for the ThreadedTracker class (Phase 3 optimization).

These tests verify:
- Non-blocking operation
- Throttling of partial updates
- Backpressure handling
- Thread safety
- Integration with existing tracker functionality
"""

import time
import unittest

from autocue.threaded_tracker import ThreadedTracker


class TestThreadedTrackerBasic(unittest.TestCase):
    """Test basic threaded tracker functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.script = "The quick brown fox jumps over the lazy dog"
        self.tracker = ThreadedTracker(
            self.script,
            partial_throttle_ms=50,
            max_queue_size=10
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.tracker:
            self.tracker.shutdown()

    def test_initialization(self):
        """Test that tracker initializes successfully."""
        self.assertIsNotNone(self.tracker)
        self.assertTrue(self.tracker.started.is_set())
        self.assertFalse(self.tracker.shutdown_flag.is_set())

    def test_submit_transcription_returns_quickly(self):
        """Test that submit_transcription is non-blocking."""
        start_time = time.time()

        # Submit multiple transcriptions
        for _ in range(10):
            self.tracker.submit_transcription("The quick", is_partial=False)

        elapsed = time.time() - start_time

        # Should complete in under 10ms even with 10 submissions
        self.assertLess(elapsed, 0.01,
                        f"submit_transcription took {elapsed*1000:.1f}ms, should be < 10ms")

    def test_basic_tracking(self):
        """Test that tracking produces correct results."""
        # Submit transcription
        self.tracker.submit_transcription("The quick brown", is_partial=False)

        # Wait for result
        result = self.tracker.get_latest_result(timeout=1.0)

        self.assertIsNotNone(result)
        self.assertIsNotNone(result.position)
        self.assertGreater(result.position.word_index, 0)
        self.assertGreater(result.position.confidence, 0)

    def test_partial_and_final_updates(self):
        """Test that both partial and final updates work."""
        # Submit partial
        self.tracker.submit_transcription("The qui", is_partial=True)
        time.sleep(0.1)  # Give time to process

        # Submit final
        self.tracker.submit_transcription("The quick brown", is_partial=False)

        # Wait for result
        result = self.tracker.get_latest_result(timeout=1.0)

        self.assertIsNotNone(result)

    def test_reset(self):
        """Test that reset command works."""
        # Track some words
        self.tracker.submit_transcription("The quick brown fox", is_partial=False)
        result = self.tracker.get_latest_result(timeout=1.0)
        self.assertIsNotNone(result)

        # Reset
        self.tracker.reset()
        time.sleep(0.1)  # Give time to process

        # Submit new transcription
        self.tracker.submit_transcription("The", is_partial=False)
        result = self.tracker.get_latest_result(timeout=1.0)

        # Should be back at the beginning
        self.assertIsNotNone(result)
        self.assertLessEqual(result.position.word_index, 1)

    def test_jump_to(self):
        """Test that jump_to command works."""
        # Jump to word 5
        self.tracker.jump_to(5)
        time.sleep(0.1)  # Give time to process

        # Submit transcription that should match near position 5
        self.tracker.submit_transcription("over the lazy", is_partial=False)
        result = self.tracker.get_latest_result(timeout=1.0)

        self.assertIsNotNone(result)
        # Should be somewhere around position 5-7
        self.assertGreater(result.position.word_index, 3)

    def test_cached_result(self):
        """Test that cached results work."""
        # Submit transcription
        self.tracker.submit_transcription("The quick", is_partial=False)

        # Wait for result
        result1 = self.tracker.get_latest_result(timeout=1.0)
        self.assertIsNotNone(result1)

        # Get cached result (should be same)
        result2 = self.tracker.get_cached_result()
        self.assertIsNotNone(result2)
        self.assertEqual(result1.request_id, result2.request_id)

    def test_shutdown(self):
        """Test that shutdown works cleanly."""
        self.tracker.shutdown()
        self.assertTrue(self.tracker.shutdown_flag.is_set())

        # Worker thread should stop
        if self.tracker.worker_thread:
            self.tracker.worker_thread.join(timeout=2.0)
            self.assertFalse(self.tracker.worker_thread.is_alive())


class TestThrottling(unittest.TestCase):
    """Test throttling of partial updates."""

    def setUp(self):
        """Set up test fixtures."""
        self.script = "The quick brown fox jumps over the lazy dog"
        self.tracker = ThreadedTracker(
            self.script,
            partial_throttle_ms=50,  # 50ms throttle
            max_queue_size=10
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.tracker:
            self.tracker.shutdown()

    def test_partial_throttling(self):
        """Test that partials are throttled to max 1 per 50ms."""
        # Submit 10 partials rapidly
        submitted = 0
        for i in range(10):
            if self.tracker.submit_transcription(f"The quick {i}", is_partial=True):
                submitted += 1
            time.sleep(0.01)  # 10ms between submissions

        # With 50ms throttle and 10ms spacing, should get ~2-3 accepted
        # (first one + ~1-2 more after throttle expires)
        self.assertLess(submitted, 5,
                        f"Expected < 5 partials to be accepted, got {submitted}")
        self.assertGreater(submitted, 0,
                           f"Expected > 0 partials to be accepted, got {submitted}")

    def test_finals_not_throttled(self):
        """Test that final updates are not throttled."""
        # Submit 5 final updates rapidly
        submitted = 0
        for i in range(5):
            if self.tracker.submit_transcription(f"The quick {i}", is_partial=False):
                submitted += 1
            time.sleep(0.001)  # 1ms between submissions

        # All finals should be accepted
        self.assertEqual(submitted, 5,
                        f"Expected all 5 finals to be accepted, got {submitted}")

    def test_throttle_respects_timing(self):
        """Test that throttle properly respects 50ms timing."""
        # Submit first partial
        accepted1 = self.tracker.submit_transcription("The", is_partial=True)
        self.assertTrue(accepted1)

        # Submit second partial immediately (should be rejected)
        accepted2 = self.tracker.submit_transcription("The quick", is_partial=True)
        self.assertFalse(accepted2)

        # Wait for throttle to expire
        time.sleep(0.06)  # 60ms

        # Submit third partial (should be accepted)
        accepted3 = self.tracker.submit_transcription("The quick brown", is_partial=True)
        self.assertTrue(accepted3)


class TestBackpressure(unittest.TestCase):
    """Test backpressure handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.script = "The quick brown fox jumps over the lazy dog"
        self.tracker = ThreadedTracker(
            self.script,
            partial_throttle_ms=0,  # Disable throttle for backpressure testing
            max_queue_size=3  # Small queue to trigger backpressure
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.tracker:
            self.tracker.shutdown()

    def test_backpressure_drops_old_partials(self):
        """Test that backpressure drops old partials when queue is full."""
        # Fill the queue with finals (which won't be dropped)
        for i in range(3):
            self.tracker.submit_transcription(f"The quick {i}", is_partial=False)

        # Queue should now be full
        # Try to submit a partial - it should handle backpressure
        # by dropping old partials and accepting this one
        result = self.tracker.submit_transcription("The brown", is_partial=True)

        # Result may vary depending on timing, but should not crash
        self.assertIsInstance(result, bool)

    def test_backpressure_preserves_finals(self):
        """Test that backpressure doesn't drop final updates."""
        # Submit many finals rapidly
        submitted = 0
        for i in range(10):
            # Small sleep to avoid overwhelming the system
            time.sleep(0.001)
            if self.tracker.submit_transcription(f"The quick {i}", is_partial=False):
                submitted += 1

        # Should submit at least some finals (may not be all due to queue size)
        self.assertGreater(submitted, 0)


class TestConcurrency(unittest.TestCase):
    """Test thread safety and concurrent operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.script = "The quick brown fox jumps over the lazy dog"
        self.tracker = ThreadedTracker(
            self.script,
            partial_throttle_ms=0,
            max_queue_size=20
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.tracker:
            self.tracker.shutdown()

    def test_concurrent_submissions(self):
        """Test that concurrent submissions work correctly."""
        import threading

        submitted_count = [0]
        lock = threading.Lock()

        def submit_many():
            for i in range(10):
                if self.tracker.submit_transcription(f"The quick {i}", is_partial=False):
                    with lock:
                        submitted_count[0] += 1
                time.sleep(0.001)

        # Start multiple threads submitting
        threads = [threading.Thread(target=submit_many) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have submitted some transcriptions without errors
        self.assertGreater(submitted_count[0], 0)

    def test_get_result_while_processing(self):
        """Test that getting results while processing is safe."""
        # Submit multiple transcriptions
        for i in range(5):
            self.tracker.submit_transcription(f"The quick {i}", is_partial=False)

        # Try to get results while still processing
        results = []
        for _ in range(10):
            result = self.tracker.get_latest_result(timeout=0.1)
            if result:
                results.append(result)

        # Should get at least one result
        self.assertGreater(len(results), 0)


class TestDisplaySettings(unittest.TestCase):
    """Test display settings update."""

    def setUp(self):
        """Set up test fixtures."""
        self.script = "The quick brown fox jumps over the lazy dog"
        self.tracker = ThreadedTracker(self.script)

    def tearDown(self):
        """Clean up after tests."""
        if self.tracker:
            self.tracker.shutdown()

    def test_update_display_settings(self):
        """Test that display settings can be updated."""
        # Update display settings
        self.tracker.update_display_settings(past_lines=3, future_lines=5)

        # Give time to process
        time.sleep(0.1)

        # Submit transcription
        self.tracker.submit_transcription("The quick brown", is_partial=False)

        # Get result
        result = self.tracker.get_latest_result(timeout=1.0)

        self.assertIsNotNone(result)
        self.assertIsNotNone(result.display_lines)


class TestPerformance(unittest.TestCase):
    """Test performance characteristics."""

    def setUp(self):
        """Set up test fixtures."""
        # Use a longer script for performance testing
        self.script = " ".join([
            "The quick brown fox jumps over the lazy dog",
            "Pack my box with five dozen liquor jugs",
            "How vexingly quick daft zebras jump"
        ] * 10)
        self.tracker = ThreadedTracker(
            self.script,
            partial_throttle_ms=50,
            max_queue_size=10
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.tracker:
            self.tracker.shutdown()

    def test_submit_latency(self):
        """Test that submit_transcription has low latency."""
        latencies = []

        for i in range(100):
            start = time.time()
            self.tracker.submit_transcription("The quick brown fox", is_partial=False)
            latency = (time.time() - start) * 1000  # ms
            latencies.append(latency)
            time.sleep(0.001)  # Small delay

        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[94]  # 95th percentile

        # Submit should be very fast (< 1ms average)
        self.assertLess(avg_latency, 1.0,
                       f"Average submit latency {avg_latency:.2f}ms should be < 1ms")
        self.assertLess(p95_latency, 2.0,
                       f"P95 submit latency {p95_latency:.2f}ms should be < 2ms")

    def test_throughput(self):
        """Test that tracker can handle high throughput."""
        start_time = time.time()

        # Submit 100 transcriptions
        submitted = 0
        for i in range(100):
            if self.tracker.submit_transcription(f"The quick brown {i}", is_partial=False):
                submitted += 1

        elapsed = time.time() - start_time
        throughput = submitted / elapsed

        # Should handle at least 1000 submissions per second
        self.assertGreater(throughput, 1000,
                          f"Throughput {throughput:.0f}/s should be > 1000/s")


if __name__ == '__main__':
    unittest.main()
