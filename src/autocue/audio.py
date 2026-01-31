# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Audio capture module using sounddevice for low-latency microphone input.
Captures audio in small chunks and feeds them to the transcriber.
"""

import queue
import time as time_m
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
    _device_sample_rate: int
    _needs_resample: bool
    _capture_dtype: type[np.int16] | type[np.float32]
    _needs_dtype_convert: bool

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

        self._device_sample_rate = sample_rate
        self._needs_resample = False
        self._capture_dtype: type[np.int16] | type[np.float32] = np.int16
        self._needs_dtype_convert = False

    def _convert_audio(self, indata: npt.NDArray[Any]) -> bytes:
        """Convert captured audio to int16 at the target sample rate."""
        data: npt.NDArray[np.int16]

        if self._needs_dtype_convert:
            # float32 [-1.0, 1.0] -> int16
            data = (np.frombuffer(indata, dtype=np.float32) * 32767).astype(
                np.int16)
        else:
            data = np.frombuffer(indata, dtype=np.int16)

        if self._needs_resample:
            # Resample from device rate to target rate using linear interpolation
            n_input = len(data)
            n_output = int(n_input * self.sample_rate / self._device_sample_rate)
            x_old = np.linspace(0, 1, n_input)
            x_new = np.linspace(0, 1, n_output)
            data = np.interp(x_new, x_old, data.astype(np.float64)).astype(
                np.int16)

        return bytes(data)

    def _audio_callback(
        self,
        indata: npt.NDArray[Any],
        frames: int,
        time: Any,
        status: sd.CallbackFlags
    ) -> None:
        """Called for each audio chunk from the microphone."""
        if status:
            print(f"Audio status: {status}")

        if self._needs_resample or self._needs_dtype_convert:
            self.audio_queue.put(self._convert_audio(indata))
        else:
            self.audio_queue.put(bytes(indata))

    def _try_open_stream(
        self,
        samplerate: int,
        blocksize: int,
        dtype: type[np.int16] | type[np.float32],
    ) -> sd.RawInputStream:
        """Attempt to open a RawInputStream with the given parameters."""
        return sd.RawInputStream(
            samplerate=samplerate,
            blocksize=blocksize,
            device=self.device,
            dtype=dtype,
            channels=1,
            callback=self._audio_callback,
        )

    def start(self) -> None:
        """Start capturing audio from the microphone."""
        if self.running:
            return

        start_time = time_m.time()
        print("[AUDIO] Starting audio capture...")

        self.running = True
        stream_create_start = time_m.time()

        # Try 1: target rate (16000 Hz) with int16
        try:
            self.stream = self._try_open_stream(
                self.sample_rate, self.chunk_size, np.int16)
        except sd.PortAudioError as e1:
            print(f"[AUDIO] Cannot open at {self.sample_rate} Hz int16: {e1}")

            # Query device's default sample rate
            dev_info: dict[str, Any] = dict(
                sd.query_devices(
                    self.device if self.device is not None
                    else sd.default.device[0],
                    'input',
                )  # type: ignore[arg-type]
            )
            native_rate = int(dev_info.get('default_samplerate', 44100))
            native_blocksize = int(
                native_rate * self.chunk_duration_ms / 1000)

            # Try 2: device's native rate with int16
            try:
                self.stream = self._try_open_stream(
                    native_rate, native_blocksize, np.int16)
                self._device_sample_rate = native_rate
                self._needs_resample = True
                print(
                    f"[AUDIO] Opened at {native_rate} Hz int16"
                    " (will resample to"
                    f" {self.sample_rate} Hz)")
            except sd.PortAudioError as e2:
                print(
                    f"[AUDIO] Cannot open at {native_rate} Hz int16: {e2}")

                # Try 3: device's native rate with float32
                self.stream = self._try_open_stream(
                    native_rate, native_blocksize, np.float32)
                self._device_sample_rate = native_rate
                self._needs_resample = True
                self._capture_dtype = np.float32
                self._needs_dtype_convert = True
                print(
                    f"[AUDIO] Opened at {native_rate} Hz float32"
                    " (will convert and resample to"
                    f" {self.sample_rate} Hz int16)")

        print(
            f"[AUDIO] RawInputStream created in {time_m.time() - stream_create_start:.3f}s")

        stream_start_time = time_m.time()
        self.stream.start()
        print(
            f"[AUDIO] stream.start() took {time_m.time() - stream_start_time:.3f}s")
        print(
            f"[AUDIO] Total audio start time: {time_m.time() - start_time:.3f}s")

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


def _get_default_hostapi_index() -> int:
    """Get the index of the default host API."""
    hostapis = sd.query_hostapis()
    for i, api in enumerate(hostapis):
        api_dict: dict[str, Any] = dict(api)  # type: ignore[arg-type]
        if api_dict.get('name', '') == 'Windows WASAPI':
            return i
    # Fall back to the host API of the default input device
    default_dev: dict[str, Any] = dict(
        sd.query_devices(kind='input')  # type: ignore[arg-type]
    )
    return int(default_dev.get('hostapi', 0))


def list_devices() -> Sequence[Any]:
    """List available, enabled audio input devices."""
    print("Available audio input devices:")
    devices: Sequence[Any] = sd.query_devices()
    hostapi_index: int = _get_default_hostapi_index()
    for i, device in enumerate(devices):
        # Convert device info to dict for easier access
        # type: ignore[arg-type, assignment]
        dev: dict[str, Any] = dict(device)
        if dev.get('hostapi') != hostapi_index:
            continue
        if dev.get('max_input_channels', 0) > 0:
            print(f"  [{i}] {dev.get('name', 'Unknown')} "
                  f"(inputs: {dev.get('max_input_channels', 0)})")
    return devices
