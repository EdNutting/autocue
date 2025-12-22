"""Tests for the transcription module, including Vosk artifact filtering."""

import json
from unittest.mock import Mock, MagicMock
from src.autocue.transcribe import Transcriber, TranscriptionResult


class TestVoskArtifactFiltering:
    """Test that Vosk artifacts like 'the' are filtered out."""

    def setup_method(self):
        """Set up a transcriber with mocked Vosk components for testing."""
        # Create a mock transcriber without actually loading the model
        self.transcriber = object.__new__(Transcriber)
        self.transcriber.sample_rate = 16000

        # Mock the recognizer
        self.transcriber.recognizer = Mock()
        self.transcriber.model = Mock()

    def test_filters_single_word_the_final(self):
        """Verify that final result containing only 'the' is filtered out."""
        # Simulate Vosk returning "the" as a final result
        self.transcriber.recognizer.AcceptWaveform.return_value = True
        self.transcriber.recognizer.Result.return_value = json.dumps({"text": "the"})

        result = self.transcriber.process_audio(b"fake_audio_data")

        # Should return None (filtered out)
        assert result is None

    def test_filters_single_word_the_partial(self):
        """Verify that partial result containing only 'the' is filtered out."""
        # Simulate Vosk returning "the" as a partial result
        self.transcriber.recognizer.AcceptWaveform.return_value = False
        self.transcriber.recognizer.PartialResult.return_value = json.dumps({"partial": "the"})

        result = self.transcriber.process_audio(b"fake_audio_data")

        # Should return None (filtered out)
        assert result is None

    def test_filters_single_word_the_case_insensitive(self):
        """Verify that 'THE' (uppercase) is also filtered out."""
        # Test uppercase
        self.transcriber.recognizer.AcceptWaveform.return_value = True
        self.transcriber.recognizer.Result.return_value = json.dumps({"text": "THE"})

        result = self.transcriber.process_audio(b"fake_audio_data")
        assert result is None

        # Test mixed case
        self.transcriber.recognizer.Result.return_value = json.dumps({"text": "The"})
        result = self.transcriber.process_audio(b"fake_audio_data")
        assert result is None

    def test_allows_the_in_phrases(self):
        """Verify that phrases containing 'the' are NOT filtered out."""
        # "the cat" should not be filtered
        self.transcriber.recognizer.AcceptWaveform.return_value = True
        self.transcriber.recognizer.Result.return_value = json.dumps({"text": "the cat"})

        result = self.transcriber.process_audio(b"fake_audio_data")

        # Should return the full phrase
        assert result is not None
        assert result.text == "the cat"
        assert result.is_partial is False

    def test_allows_normal_transcription(self):
        """Verify that normal transcription still works."""
        # Test a normal phrase
        self.transcriber.recognizer.AcceptWaveform.return_value = False
        self.transcriber.recognizer.PartialResult.return_value = json.dumps(
            {"partial": "hello world"}
        )

        result = self.transcriber.process_audio(b"fake_audio_data")

        assert result is not None
        assert result.text == "hello world"
        assert result.is_partial is True

    def test_filters_the_from_get_final(self):
        """Verify that get_final() also filters out 'the'."""
        self.transcriber.recognizer.FinalResult.return_value = json.dumps({"text": "the"})

        result = self.transcriber.get_final()

        # Should return None (filtered out)
        assert result is None

    def test_allows_normal_text_from_get_final(self):
        """Verify that get_final() returns normal text."""
        self.transcriber.recognizer.FinalResult.return_value = json.dumps(
            {"text": "final words"}
        )

        result = self.transcriber.get_final()

        assert result is not None
        assert result.text == "final words"
        assert result.is_partial is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
