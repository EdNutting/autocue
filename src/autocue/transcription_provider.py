"""
Base interface for speech transcription providers.

This module defines the abstract interface that all transcription providers
(Vosk, Sherpa-ONNX, etc.) must implement.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    """Represents a transcription result from any provider."""

    text: str
    is_partial: bool
    confidence: float = 1.0

    def __repr__(self) -> str:
        status: str = "partial" if self.is_partial else "final"
        return f"TranscriptionResult({status}: '{self.text}')"


@dataclass
class ModelInfo:
    """Information about an available transcription model."""

    id: str  # Unique identifier (e.g., "vosk-en-us-small")
    name: str  # Display name (e.g., "English US - Small")
    provider: str  # Provider name ("vosk" or "sherpa")
    size_mb: int | None = None
    description: str | None = None


class TranscriptionProvider(ABC):
    """Base interface for speech transcription providers."""

    @abstractmethod
    def __init__(self, model_id: str, sample_rate: int = 16000) -> None:
        """
        Initialize the provider with a specific model.

        Args:
            model_id: Unique model identifier (e.g., "vosk-en-us-small")
            sample_rate: Audio sample rate in Hz (default: 16000)
        """

    @abstractmethod
    def process_audio(self, audio_data: bytes) -> TranscriptionResult | None:
        """
        Process an audio chunk and return transcription result.

        Args:
            audio_data: Raw audio bytes (16-bit PCM, mono)

        Returns:
            TranscriptionResult with partial or final text, or None if no speech
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset the recognizer state (e.g., after a long pause)."""

    @abstractmethod
    def get_final(self) -> TranscriptionResult | None:
        """Get any remaining buffered speech as final result."""

    @staticmethod
    @abstractmethod
    def get_available_models() -> list[ModelInfo]:
        """
        Get list of available models for this provider.

        Returns:
            List of ModelInfo objects describing available models
        """

    @staticmethod
    @abstractmethod
    def download_model(model_id: str, target_dir: str | None = None,
                       progress_callback: Callable[[str, int], None] | None = None) -> str:
        """
        Download a model if not already present.

        Args:
            model_id: Model identifier to download
            target_dir: Optional target directory, or None for default

        Returns:
            Path to the downloaded model directory
        """
