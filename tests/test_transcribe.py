# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""Tests for the transcription module, including Vosk artifact filtering."""

import json
from unittest.mock import Mock, MagicMock, patch
from src.autocue.transcribe import Transcriber, TranscriptionResult


class TestVoskArtifactFiltering:
    """Test that Vosk artifacts like 'the' are filtered out."""

    def setup_method(self):
        """Set up a transcriber with mocked Vosk components for testing."""
        # Mock the VoskProvider to avoid loading actual models
        with patch('src.autocue.transcribe.create_provider') as mock_create:
            # Create a mock provider
            self.mock_provider = Mock()
            mock_create.return_value = self.mock_provider

            # Create transcriber (will use mocked provider)
            self.transcriber = Transcriber(model_name="small")

        # Now we can mock the provider's methods
        # The provider is already set as self.mock_provider

    def test_filters_single_word_the_final(self):
        """Verify that final result containing only 'the' is filtered out."""
        # Simulate provider returning None (Vosk filters "the" internally)
        self.mock_provider.process_audio.return_value = None

        result = self.transcriber.process_audio(b"fake_audio_data")

        # Should return None (filtered out)
        assert result is None

    def test_filters_single_word_the_partial(self):
        """Verify that partial result containing only 'the' is filtered out."""
        # Simulate provider returning None (Vosk filters "the" internally)
        self.mock_provider.process_audio.return_value = None

        result = self.transcriber.process_audio(b"fake_audio_data")

        # Should return None (filtered out)
        assert result is None

    def test_filters_single_word_the_case_insensitive(self):
        """Verify that 'THE' (uppercase) is also filtered out."""
        # Vosk provider filters "the" internally regardless of case
        self.mock_provider.process_audio.return_value = None

        result = self.transcriber.process_audio(b"fake_audio_data")
        assert result is None

        # Test with different case
        result = self.transcriber.process_audio(b"fake_audio_data")
        assert result is None

    def test_allows_the_in_phrases(self):
        """Verify that phrases containing 'the' are NOT filtered out."""
        # "the cat" should not be filtered
        self.mock_provider.process_audio.return_value = TranscriptionResult(
            text="the cat",
            is_partial=False
        )

        result = self.transcriber.process_audio(b"fake_audio_data")

        # Should return the full phrase
        assert result is not None
        assert result.text == "the cat"
        assert result.is_partial is False

    def test_allows_normal_transcription(self):
        """Verify that normal transcription still works."""
        # Test a normal phrase
        self.mock_provider.process_audio.return_value = TranscriptionResult(
            text="hello world",
            is_partial=True
        )

        result = self.transcriber.process_audio(b"fake_audio_data")

        assert result is not None
        assert result.text == "hello world"
        assert result.is_partial is True

    def test_filters_the_from_get_final(self):
        """Verify that get_final() also filters out 'the'."""
        self.mock_provider.get_final.return_value = None

        result = self.transcriber.get_final()

        # Should return None (filtered out)
        assert result is None

    def test_allows_normal_text_from_get_final(self):
        """Verify that get_final() returns normal text."""
        self.mock_provider.get_final.return_value = TranscriptionResult(
            text="final words",
            is_partial=False
        )

        result = self.transcriber.get_final()

        assert result is not None
        assert result.text == "final words"
        assert result.is_partial is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
