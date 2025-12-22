"""Tests for the Sherpa-ONNX transcription provider."""

from unittest.mock import Mock, MagicMock, patch
import pytest

from src.autocue.transcription_provider import TranscriptionResult


class TestSherpaProviderAPICompatibility:
    """Test that SherpaProvider handles both old and new sherpa-onnx API versions."""

    def setup_method(self):
        """Set up a SherpaProvider with mocked sherpa-onnx components."""
        # Mock the sherpa_onnx module
        self.mock_sherpa_onnx = MagicMock()

        # Mock the recognizer and stream
        self.mock_recognizer = Mock()
        self.mock_stream = Mock()

        # Patch sherpa-onnx availability and import
        with patch.dict('sys.modules', {'sherpa_onnx': self.mock_sherpa_onnx}):
            with patch('src.autocue.providers.sherpa_provider.SHERPA_AVAILABLE', True):
                with patch('src.autocue.providers.sherpa_provider.sherpa_onnx', self.mock_sherpa_onnx):
                    # Mock the model path check
                    with patch('os.path.exists', return_value=True):
                        # Mock the recognizer creation
                        with patch.object(
                            __import__('src.autocue.providers.sherpa_provider', fromlist=['SherpaProvider']).SherpaProvider,
                            '_create_recognizer',
                            return_value=self.mock_recognizer
                        ):
                            from src.autocue.providers.sherpa_provider import SherpaProvider

                            self.mock_recognizer.create_stream.return_value = self.mock_stream
                            self.provider = SherpaProvider(
                                model_id="sherpa-zipformer-en-2023-06-26",
                                sample_rate=16000
                            )

    def test_process_audio_with_string_result(self):
        """Verify that process_audio handles new API where get_result returns a string."""
        # Configure mock for new API: get_result returns a string directly
        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = "hello world"

        result = self.provider.process_audio(b"\x00\x00" * 160)

        assert result is not None
        assert isinstance(result, TranscriptionResult)
        assert result.text == "hello world"
        # Sherpa returns final results, not partial
        assert result.is_partial is False

    def test_process_audio_with_object_result(self):
        """Verify that process_audio handles old API where get_result returns an object with .text."""
        # Configure mock for old API: get_result returns an object with .text attribute
        mock_result = Mock()
        mock_result.text = "hello world"

        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = mock_result

        result = self.provider.process_audio(b"\x00\x00" * 160)

        assert result is not None
        assert isinstance(result, TranscriptionResult)
        assert result.text == "hello world"
        # Sherpa returns final results, not partial
        assert result.is_partial is False

    def test_process_audio_with_empty_string_result(self):
        """Verify that process_audio returns None when result is empty string."""
        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = ""

        result = self.provider.process_audio(b"\x00\x00" * 160)

        assert result is None

    def test_process_audio_with_empty_object_result(self):
        """Verify that process_audio returns None when result.text is empty."""
        mock_result = Mock()
        mock_result.text = ""

        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = mock_result

        result = self.provider.process_audio(b"\x00\x00" * 160)

        assert result is None

    def test_get_final_with_string_result(self):
        """Verify that get_final handles new API where get_result returns a string."""
        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = "final text"

        result = self.provider.get_final()

        assert result is not None
        assert isinstance(result, TranscriptionResult)
        assert result.text == "final text"
        assert result.is_partial is False

    def test_get_final_with_object_result(self):
        """Verify that get_final handles old API where get_result returns an object with .text."""
        mock_result = Mock()
        mock_result.text = "final text"

        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = mock_result

        result = self.provider.get_final()

        assert result is not None
        assert isinstance(result, TranscriptionResult)
        assert result.text == "final text"
        assert result.is_partial is False

    def test_get_final_with_empty_result(self):
        """Verify that get_final returns None when result is empty."""
        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = ""

        result = self.provider.get_final()

        assert result is None

    def test_process_audio_always_returns_final(self):
        """Verify that process_audio returns final results (Sherpa behavior)."""
        # Sherpa returns final results immediately, not partial results
        self.mock_recognizer.is_ready.return_value = False
        self.mock_recognizer.get_result.return_value = "streaming text"

        result = self.provider.process_audio(b"\x00\x00" * 160)

        assert result is not None
        assert result.is_partial is False
        assert result.text == "streaming text"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
