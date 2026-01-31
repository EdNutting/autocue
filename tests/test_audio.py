# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""Tests for the AudioCapture audio conversion and resampling logic."""

import numpy as np
import pytest

from autocue.audio import AudioCapture


class TestConvertAudio:
    """Tests for AudioCapture._convert_audio."""

    def _make_capture(self) -> AudioCapture:
        """Create an AudioCapture without starting it."""
        return AudioCapture(sample_rate=16000, chunk_duration_ms=100, device=None)

    def test_passthrough_no_conversion(self):
        """When no resampling or dtype conversion is needed, bytes pass through unchanged."""
        capture = self._make_capture()
        # Default state: no resample, no dtype convert
        original = np.array([0, 1000, -1000, 32767, -32768], dtype=np.int16)
        result = capture._convert_audio(original)
        assert result == bytes(original)

    def test_resample_halves_samples(self):
        """Resampling from 32000 Hz to 16000 Hz should produce half the samples."""
        capture = self._make_capture()
        capture._device_sample_rate = 32000
        capture._needs_resample = True

        n_input = 320  # 10ms at 32000 Hz
        original = np.zeros(n_input, dtype=np.int16)
        result = capture._convert_audio(original)

        result_array = np.frombuffer(result, dtype=np.int16)
        expected_output = int(n_input * 16000 / 32000)
        assert len(result_array) == expected_output

    def test_resample_48000_to_16000(self):
        """Resampling from 48000 Hz to 16000 Hz should produce 1/3 the samples."""
        capture = self._make_capture()
        capture._device_sample_rate = 48000
        capture._needs_resample = True

        n_input = 480  # 10ms at 48000 Hz
        original = np.zeros(n_input, dtype=np.int16)
        result = capture._convert_audio(original)

        result_array = np.frombuffer(result, dtype=np.int16)
        expected_output = int(n_input * 16000 / 48000)
        assert len(result_array) == expected_output

    def test_resample_preserves_dc_signal(self):
        """A constant signal should remain constant after resampling."""
        capture = self._make_capture()
        capture._device_sample_rate = 48000
        capture._needs_resample = True

        n_input = 480
        value = 12345
        original = np.full(n_input, value, dtype=np.int16)
        result = capture._convert_audio(original)

        result_array = np.frombuffer(result, dtype=np.int16)
        np.testing.assert_array_equal(result_array, value)

    def test_float32_to_int16_conversion(self):
        """Float32 audio should be converted to int16 range."""
        capture = self._make_capture()
        capture._needs_dtype_convert = True
        capture._capture_dtype = np.float32

        # float32 full scale
        original = np.array([0.0, 1.0, -1.0, 0.5, -0.5], dtype=np.float32)
        result = capture._convert_audio(original)

        result_array = np.frombuffer(result, dtype=np.int16)
        assert len(result_array) == 5
        assert result_array[0] == 0
        assert result_array[1] == 32767
        assert result_array[2] == -32767
        assert abs(result_array[3] - 16383) <= 1
        assert abs(result_array[4] - (-16383)) <= 1

    def test_float32_with_resample(self):
        """Float32 conversion combined with resampling should produce correct output."""
        capture = self._make_capture()
        capture._device_sample_rate = 48000
        capture._needs_resample = True
        capture._needs_dtype_convert = True
        capture._capture_dtype = np.float32

        n_input = 480  # 10ms at 48000 Hz
        original = np.full(n_input, 0.5, dtype=np.float32)
        result = capture._convert_audio(original)

        result_array = np.frombuffer(result, dtype=np.int16)
        expected_output = int(n_input * 16000 / 48000)
        assert len(result_array) == expected_output
        # All values should be approximately 0.5 * 32767 = 16383
        np.testing.assert_allclose(result_array, 16383, atol=1)
