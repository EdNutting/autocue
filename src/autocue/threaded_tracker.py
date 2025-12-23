# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Threaded wrapper for ScriptTracker that enables non-blocking operation.

This module implements Phase 3 of the performance optimization plan by moving
tracking to a separate thread with queue-based communication. This ensures
audio capture and transcription are never blocked by tracking operations.
"""

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

from .tracker import ScriptLine, ScriptPosition, ScriptTracker

logger = logging.getLogger(__name__)


@dataclass
class TrackingRequest:
    """A request to update tracking position."""
    transcription: str
    is_partial: bool
    timestamp: float
    request_id: int


@dataclass
class TrackingResult:
    """Result from a tracking update."""
    position: ScriptPosition
    display_lines: list[ScriptLine]
    current_line_idx: int
    word_offset: int
    request_id: int
    processing_time: float


@dataclass
class ControlCommand:
    """Control command for the worker thread."""
    command: str  # 'reset', 'jump_to', 'shutdown', 'update_display_settings'
    param: Any = None


class ThreadedTracker:
    """
    Thread-safe wrapper around ScriptTracker for non-blocking operation.

    Features:
    - Non-blocking update() that queues transcriptions
    - Automatic throttling of partial updates (max 1 per 50ms)
    - Backpressure handling (drops old partials when queue is full)
    - Worker thread processes tracking in parallel
    - Cached results for immediate access

    Usage:
        tracker = ThreadedTracker(script_text)

        # Non-blocking update
        tracker.submit_transcription(text, is_partial=True)

        # Poll for results
        result = tracker.get_latest_result()
        if result:
            # New position available
            send_to_ui(result.position)
    """

    def __init__(
        self,
        script_text: str,
        window_size: int = 8,
        match_threshold: float = 65.0,
        jump_threshold: int = 3,
        max_jump_distance: int = 50,
        partial_throttle_ms: int = 50,
        max_queue_size: int = 10
    ):
        """
        Initialize the threaded tracker.

        Args:
            script_text: The script text to track
            window_size: Window size for matching
            match_threshold: Match threshold for fuzzy matching
            jump_threshold: Threshold for jump detection
            max_jump_distance: Maximum jump distance
            partial_throttle_ms: Minimum time between partial updates (default: 50ms)
            max_queue_size: Maximum queue size before backpressure kicks in (default: 10)
        """
        self.script_text = script_text
        self.window_size = window_size
        self.match_threshold = match_threshold
        self.jump_threshold = jump_threshold
        self.max_jump_distance = max_jump_distance
        self.partial_throttle_ms = partial_throttle_ms
        self.max_queue_size = max_queue_size

        # Queues for communication
        self.request_queue: queue.Queue[TrackingRequest | ControlCommand] = queue.Queue(
            maxsize=max_queue_size
        )
        self.result_queue: queue.Queue[TrackingResult] = queue.Queue()

        # Thread control
        self.worker_thread: threading.Thread | None = None
        self.shutdown_flag = threading.Event()
        self.started = threading.Event()

        # Cached state (thread-safe with lock)
        self.state_lock = threading.Lock()
        self.latest_result: TrackingResult | None = None
        self.request_counter = 0
        self.last_partial_time = 0.0

        # Display settings cache
        self.past_lines = 1
        self.future_lines = 8

        # Start worker thread
        self._start_worker()

        # Wait for worker to be ready
        self.started.wait(timeout=5.0)
        if not self.started.is_set():
            raise RuntimeError("Worker thread failed to start")

    def _start_worker(self) -> None:
        """Start the worker thread."""
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name="TrackerWorker",
            daemon=True
        )
        self.worker_thread.start()

    def _worker_loop(self) -> None:
        """Main loop for the worker thread."""
        try:
            # Create the actual tracker in the worker thread
            tracker = ScriptTracker(
                self.script_text,
                window_size=self.window_size,
                match_threshold=self.match_threshold,
                jump_threshold=self.jump_threshold,
                max_jump_distance=self.max_jump_distance
            )

            logger.info("ThreadedTracker worker started")
            self.started.set()

            while not self.shutdown_flag.is_set():
                try:
                    # Get next request with timeout to allow checking shutdown flag
                    item = self.request_queue.get(timeout=0.1)

                    if isinstance(item, ControlCommand):
                        self._handle_control_command(tracker, item)
                    elif isinstance(item, TrackingRequest):
                        self._handle_tracking_request(tracker, item)

                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error("Error in worker loop: %s", e, exc_info=True)

        finally:
            logger.info("ThreadedTracker worker stopped")

    def _handle_control_command(self, tracker: ScriptTracker, cmd: ControlCommand) -> None:
        """Handle control commands."""
        if cmd.command == 'reset':
            tracker.reset()
            logger.debug("Tracker reset")

        elif cmd.command == 'jump_to':
            tracker.jump_to(cmd.param)
            logger.debug("Tracker jumped to %d", cmd.param)

        elif cmd.command == 'update_display_settings':
            past_lines, future_lines = cmd.param
            with self.state_lock:
                self.past_lines = past_lines
                self.future_lines = future_lines
            logger.debug("Display settings updated: past=%d, future=%d", past_lines, future_lines)

        elif cmd.command == 'shutdown':
            self.shutdown_flag.set()

    def _handle_tracking_request(self, tracker: ScriptTracker, req: TrackingRequest) -> None:
        """Handle a tracking update request."""
        start_time = time.time()

        # Update tracker
        position = tracker.update(req.transcription, is_partial=req.is_partial)

        # Get display info
        with self.state_lock:
            past_lines = self.past_lines
            future_lines = self.future_lines

        display_lines, current_line_idx, word_offset = tracker.get_display_lines(
            past_lines=past_lines,
            future_lines=future_lines
        )

        processing_time = time.time() - start_time

        # Create result
        result = TrackingResult(
            position=position,
            display_lines=display_lines,
            current_line_idx=current_line_idx,
            word_offset=word_offset,
            request_id=req.request_id,
            processing_time=processing_time
        )

        # Update cached result and queue it
        with self.state_lock:
            self.latest_result = result

        # Put result in queue (non-blocking to avoid deadlock)
        try:
            self.result_queue.put_nowait(result)
        except queue.Full:
            # Drop oldest result and try again
            try:
                self.result_queue.get_nowait()
                self.result_queue.put_nowait(result)
            except (queue.Empty, queue.Full):
                pass

    def submit_transcription(self, transcription: str, is_partial: bool = False) -> bool:
        """
        Submit a transcription for tracking (non-blocking).

        Args:
            transcription: The transcription text
            is_partial: Whether this is a partial transcription

        Returns:
            True if the transcription was queued, False if it was dropped
        """
        current_time = time.time()

        # Throttle partial updates
        if is_partial:
            time_since_last = (current_time - self.last_partial_time) * 1000
            if time_since_last < self.partial_throttle_ms:
                # Too soon, drop this partial
                return False
            self.last_partial_time = current_time

        # Create request
        with self.state_lock:
            self.request_counter += 1
            request_id = self.request_counter

        request = TrackingRequest(
            transcription=transcription,
            is_partial=is_partial,
            timestamp=current_time,
            request_id=request_id
        )

        # Try to queue (with backpressure handling)
        try:
            self.request_queue.put_nowait(request)
            return True
        except queue.Full:
            # Queue is full - apply backpressure
            if is_partial:
                # Drop old partials
                dropped = 0
                while dropped < 3:  # Try to drop up to 3 items
                    try:
                        old_item = self.request_queue.get_nowait()
                        if isinstance(old_item, TrackingRequest) and old_item.is_partial:
                            dropped += 1
                        else:
                            # Put non-partial back
                            self.request_queue.put_nowait(old_item)
                            break
                    except queue.Empty:
                        break

                # Try to queue again
                try:
                    self.request_queue.put_nowait(request)
                    logger.warning("Backpressure: dropped %d old partials", dropped)
                    return True
                except queue.Full:
                    logger.warning("Backpressure: dropping current partial")
                    return False
            else:
                # Final transcription - log warning but drop it
                logger.warning("Backpressure: dropping final transcription (queue full)")
                return False

    def get_latest_result(self, timeout: float = 0) -> TrackingResult | None:
        """
        Get the latest tracking result.

        Args:
            timeout: How long to wait for a result (0 = don't wait)

        Returns:
            Latest result or None if no result available
        """
        try:
            if timeout > 0:
                return self.result_queue.get(timeout=timeout)
            else:
                return self.result_queue.get_nowait()
        except queue.Empty:
            return None

    def get_cached_result(self) -> TrackingResult | None:
        """
        Get the cached latest result without consuming from queue.

        Returns:
            Latest cached result or None
        """
        with self.state_lock:
            return self.latest_result

    def reset(self) -> None:
        """Reset tracker to the beginning."""
        cmd = ControlCommand(command='reset')
        try:
            self.request_queue.put_nowait(cmd)
        except queue.Full:
            logger.warning("Failed to queue reset command (queue full)")

    def jump_to(self, word_index: int) -> None:
        """
        Jump to a specific word index.

        Args:
            word_index: The speakable word index to jump to
        """
        cmd = ControlCommand(command='jump_to', param=word_index)
        try:
            self.request_queue.put_nowait(cmd)
        except queue.Full:
            logger.warning("Failed to queue jump_to command (queue full)")

    def update_display_settings(self, past_lines: int, future_lines: int) -> None:
        """
        Update display line settings.

        Args:
            past_lines: Number of past lines to show
            future_lines: Number of future lines to show
        """
        cmd = ControlCommand(command='update_display_settings', param=(past_lines, future_lines))
        try:
            self.request_queue.put_nowait(cmd)
        except queue.Full:
            logger.warning("Failed to queue display settings update (queue full)")

    def shutdown(self) -> None:
        """Shutdown the worker thread."""
        cmd = ControlCommand(command='shutdown')
        try:
            self.request_queue.put(cmd, timeout=1.0)
        except queue.Full:
            pass

        self.shutdown_flag.set()

        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

    def __del__(self) -> None:
        """Cleanup on deletion."""
        self.shutdown()

    @property
    def words(self) -> list[str]:
        """
        Get the word list from the tracker.

        Note: This is a convenience property but requires creating a temporary tracker.
        Consider caching this if accessed frequently.
        """
        # Create a temporary tracker to get the word list
        # This is safe since it's read-only
        temp_tracker = ScriptTracker(
            self.script_text,
            window_size=self.window_size,
            match_threshold=self.match_threshold,
            jump_threshold=self.jump_threshold,
            max_jump_distance=self.max_jump_distance
        )
        return temp_tracker.words
