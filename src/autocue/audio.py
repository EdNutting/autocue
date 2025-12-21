"""
Audio capture module using sounddevice for low-latency microphone input.
Captures audio in small chunks and feeds them to the transcriber.
"""

import queue
from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt
import sounddevice as sd


class AudioCapture:
    """Captures audio from the microphone in small chunks for streaming transcription."""

    sample_rate: int
    chunk_duration_ms: int
    chunk_size: int
    device: int | None
    audio_queue: queue.Queue[bytes]
    stream: sd.RawInputStream | None
    running: bool

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_duration_ms: int = 100,
        device: int | None = None
    ) -> None:
        """
        Initialize audio capture.

        Args:
            sample_rate: Sample rate in Hz (16000 is optimal for Vosk)
            chunk_duration_ms: Duration of each audio chunk in milliseconds
            device: Audio device index, or None for default
        """
        self.sample_rate = sample_rate
        self.chunk_duration_ms = chunk_duration_ms
        self.chunk_size = int(sample_rate * chunk_duration_ms / 1000)
        self.device = device

        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self.stream: sd.RawInputStream | None = None
        self.running = False

    def _audio_callback(
        self,
        indata: npt.NDArray[np.int16],
        frames: int,
        time: Any,
        status: sd.CallbackFlags
    ) -> None:
        """Called for each audio chunk from the microphone."""
        if status:
            print(f"Audio status: {status}")
        # Convert to bytes for Vosk
        self.audio_queue.put(bytes(indata))

    def start(self) -> None:
        """Start capturing audio from the microphone."""
        if self.running:
            return

        self.running = True
        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.chunk_size,
            device=self.device,
            dtype=np.int16,
            channels=1,
            callback=self._audio_callback
        )
        self.stream.start()

    def stop(self) -> None:
        """Stop capturing audio."""
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def get_chunk(self, timeout: float = 0.5) -> bytes | None:
        """
        Get the next audio chunk.

        Args:
            timeout: Maximum time to wait for a chunk

        Returns:
            Audio data as bytes, or None if timeout
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_queue(self) -> None:
        """Clear any pending audio chunks."""
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break


def list_devices() -> Sequence[Any]:
    """List available audio input devices."""
    print("Available audio input devices:")
    devices: Sequence[Any] = sd.query_devices()
    for i, device in enumerate(devices):
        # Convert device info to dict for easier access
        # type: ignore[arg-type, assignment]
        dev: dict[str, Any] = dict(device)
        if dev.get('max_input_channels', 0) > 0:
            print(f"  [{i}] {dev.get('name', 'Unknown')} "
                  f"(inputs: {dev.get('max_input_channels', 0)})")
    return devices
