"""
Vosk transcription provider implementation.

This module provides a Vosk-based implementation of the TranscriptionProvider interface.
"""

import json
import os
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vosk import KaldiRecognizer, Model, SetLogLevel

from ..transcription_provider import ModelInfo, TranscriptionProvider, TranscriptionResult

# Suppress Vosk's verbose logging
SetLogLevel(-1)


class VoskProvider(TranscriptionProvider):
    """Vosk speech recognition provider."""

    # Available Vosk models with metadata
    MODELS: dict[str, dict[str, Any]] = {
        # English US models
        "vosk-en-us-small": {
            "dir": "vosk-model-small-en-us-0.15",
            "name": "English US - Small",
            "size_mb": 40,
            "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        },
        "vosk-en-us-medium": {
            "dir": "vosk-model-en-us-0.22",
            "name": "English US - Medium",
            "size_mb": 1800,
            "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip",
        },
        "vosk-en-us-large": {
            "dir": "vosk-model-en-us-0.42-gigaspeech",
            "name": "English US - Large",
            "size_mb": 2300,
            "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.42-gigaspeech.zip",
        },
        # English GB models
        "vosk-en-gb-small": {
            "dir": "vosk-model-small-en-gb-0.15",
            "name": "English GB - Small",
            "size_mb": 40,
            "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-gb-0.15.zip",
        },
    }

    sample_rate: int
    model_id: str
    model_path: str
    model: Model
    recognizer: KaldiRecognizer

    def __init__(self, model_id: str, sample_rate: int = 16000) -> None:
        """
        Initialize the Vosk provider.

        Args:
            model_id: Model identifier (e.g., "vosk-en-us-small")
            sample_rate: Audio sample rate (must match audio capture)
        """
        self.sample_rate = sample_rate
        self.model_id = model_id
        self.model_path = self._get_model_path(model_id)

        print(f"Loading Vosk model from: {self.model_path}")
        if not os.path.exists(self.model_path):
            raise RuntimeError(
                f"Vosk model not found at {self.model_path}. "
                f"Please download it with: autocue --download-model {model_id}"
            )

        self.model = Model(self.model_path)
        self.recognizer = KaldiRecognizer(self.model, sample_rate)
        self.recognizer.SetWords(True)  # Include word-level timing

    def process_audio(self, audio_data: bytes) -> TranscriptionResult | None:
        """
        Process an audio chunk and return transcription result.

        Args:
            audio_data: Raw audio bytes (16-bit PCM, mono)

        Returns:
            TranscriptionResult with partial or final text, or None if no speech
        """
        if self.recognizer.AcceptWaveform(audio_data):
            # Final result - speech segment complete
            result: dict[str, Any] = json.loads(self.recognizer.Result())
            text: str = result.get("text", "").strip()
            if text and not self._is_vosk_artifact(text):
                return TranscriptionResult(text, is_partial=False)
        else:
            # Partial result - speech still in progress
            result: dict[str, Any] = json.loads(
                self.recognizer.PartialResult())
            text: str = result.get("partial", "").strip()
            if text and not self._is_vosk_artifact(text):
                return TranscriptionResult(text, is_partial=True)

        return None

    def reset(self) -> None:
        """Reset the recognizer state (e.g., after a long pause)."""
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        self.recognizer.SetWords(True)

    def get_final(self) -> TranscriptionResult | None:
        """Get any remaining buffered speech as final result."""
        result: dict[str, Any] = json.loads(self.recognizer.FinalResult())
        text: str = result.get("text", "").strip()
        if text and not self._is_vosk_artifact(text):
            return TranscriptionResult(text, is_partial=False)
        return None

    @staticmethod
    def get_available_models() -> list[ModelInfo]:
        """Get list of available Vosk models."""
        return [
            ModelInfo(
                id=model_id,
                name=info["name"],
                provider="vosk",
                size_mb=info["size_mb"],
                description=f"Vosk model - {info['name']}",
            )
            for model_id, info in VoskProvider.MODELS.items()
        ]

    @staticmethod
    def download_model(
        model_id: str,
        target_dir: str | None = None,
        progress_callback: Callable[[str, int], None] | None = None
    ) -> str:
        """
        Download a Vosk model.

        Args:
            model_id: Model identifier (e.g., "vosk-en-us-small")
            target_dir: Directory to save the model, or None for default
            progress_callback: Optional callback(stage, percent) for progress updates

        Returns:
            Path to the downloaded model as a string.
        """
        model_info: dict[str, Any] | None = VoskProvider.MODELS.get(model_id)
        if not model_info:
            raise ValueError(
                f"Unknown Vosk model: {model_id}. "
                f"Choose from: {list(VoskProvider.MODELS.keys())}"
            )

        if target_dir is None:
            target_path: Path = Path.home() / ".cache" / "autocue" / "models"
        else:
            target_path: Path = Path(target_dir)

        target_path.mkdir(parents=True, exist_ok=True)
        model_path: Path = target_path / model_info["dir"]

        if model_path.exists():
            print(f"Model already exists at {model_path}")
            if progress_callback:
                progress_callback("complete", 100)
            return str(model_path)

        url: str = model_info["url"]
        print(f"Downloading {model_id} from {url}...")
        print("This may take a few minutes depending on your connection.")

        # Create temp file and get its name, then close it before extraction
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name
            # Download with progress tracking
            if progress_callback:
                progress_callback("downloading", 0)

            def download_hook(block_count: int, block_size: int, total_size: int) -> None:
                if progress_callback and total_size > 0:
                    downloaded = block_count * block_size
                    percent = min(100, int((downloaded / total_size) * 100))
                    progress_callback("downloading", percent)

            urllib.request.urlretrieve(url, tmp_path, download_hook)

        # File handle is now closed, safe to extract and delete on Windows
        try:
            print("Extracting model...")
            if progress_callback:
                progress_callback("extracting", 0)

            with zipfile.ZipFile(tmp_path, "r") as zf:
                zf.extractall(target_path)

            if progress_callback:
                progress_callback("extracting", 100)

            print("Complete.")
            if progress_callback:
                progress_callback("complete", 100)
        finally:
            # Clean up temp file (even if extraction fails)
            print("Done. Removing temporary file...")
            try:
                os.unlink(tmp_path)
            except OSError as e:
                print(
                    f"Warning: Could not delete temporary file {tmp_path}: {e}")

        print(f"Model installed to {model_path}")
        return str(model_path)

    def _get_model_path(self, model_id: str) -> str:
        """Get the path to the model directory."""
        cache_dir: Path = Path.home() / ".cache" / "autocue" / "models"
        model_info = self.MODELS.get(model_id)
        if not model_info:
            # Assume custom model path
            return model_id
        return str(cache_dir / model_info["dir"])

    def _is_vosk_artifact(self, text: str) -> bool:
        """
        Check if the text is a known Vosk artifact from no/bad audio input.

        Vosk sometimes returns "the" when there's no valid sound input.

        Args:
            text: The transcribed text to check

        Returns:
            True if the text is a known artifact that should be filtered out
        """
        return text.lower() == "the"
