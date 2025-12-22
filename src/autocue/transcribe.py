# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Speech transcription module - compatibility wrapper.

This module provides backward compatibility for code using the old Transcriber interface.
New code should use the provider system directly from autocue.providers.
"""

from collections.abc import Callable

from .providers import create_provider
from .transcription_provider import TranscriptionResult

# Re-export TranscriptionResult for backward compatibility
__all__ = ["TranscriptionResult", "Transcriber", "download_model"]


class Transcriber:
    """
    Backward-compatible transcriber wrapper.

    This class maintains the old Transcriber API while delegating to the new provider system.
    For new code, use the provider system directly: from autocue.providers import create_provider
    """

    def __init__(
        self,
        model_path: str | None = None,
        model_name: str = "small",
        sample_rate: int = 16000,
        provider: str = "vosk",
        model_id: str | None = None,
    ) -> None:
        """
        Initialize the transcriber.

        Args:
            model_path: Path to model directory (old API, deprecated)
            model_name: Model size name (old API: "small"/"medium"/"large", deprecated)
            sample_rate: Audio sample rate (must match audio capture)
            provider: Provider name ("vosk" or "sherpa")
            model_id: New-style model identifier (e.g., "vosk-en-us-small")
        """
        # Handle backward compatibility
        if model_id is None:
            # Old-style initialization - convert to new format
            if model_path:
                # Custom model path - use as-is
                # Assume it's a Vosk model since that's what the old API supported
                self._provider = create_provider(
                    provider, model_path, sample_rate)
            else:
                # Model name - convert to new model_id format
                model_id = f"vosk-en-us-{model_name}"
                self._provider = create_provider(
                    provider, model_id, sample_rate)
        else:
            # New-style initialization
            self._provider = create_provider(provider, model_id, sample_rate)

        self.sample_rate = sample_rate

    def process_audio(self, audio_data: bytes) -> TranscriptionResult | None:
        """Process an audio chunk and return transcription result."""
        return self._provider.process_audio(audio_data)

    def reset(self) -> None:
        """Reset the recognizer state."""
        self._provider.reset()

    def get_final(self) -> TranscriptionResult | None:
        """Get any remaining buffered speech as final result."""
        return self._provider.get_final()


def download_model(model_name: str = "small", target_dir: str | None = None,
                   progress_callback: Callable[[str, int], None] | None = None) -> str:
    """
    Download a model.

    This function supports both old-style model names ("small", "medium", "large")
    and new-style model IDs ("vosk-en-us-small", "sherpa-zipformer-en-2023-06-26").

    Args:
        model_name: Model name or ID
        target_dir: Directory to save the model, or None for default

    Returns:
        Path to the downloaded model as a string.
    """
    # Detect if this is a new-style model ID or old-style name
    if model_name.startswith("vosk-"):
        # New-style Vosk model ID
        from .providers.vosk_provider import VoskProvider

        return VoskProvider.download_model(model_name, target_dir)
    elif model_name.startswith("sherpa-"):
        # Sherpa model ID
        from .providers.sherpa_provider import SherpaProvider

        return SherpaProvider.download_model(model_name, target_dir)
    else:
        # Old-style model name - convert to new format
        model_id = f"vosk-en-us-{model_name}"
        from .providers.vosk_provider import VoskProvider

        return VoskProvider.download_model(model_id, target_dir)
