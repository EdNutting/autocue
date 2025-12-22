"""
Sherpa-ONNX transcription provider implementation.

This module provides a Sherpa-ONNX-based implementation of the TranscriptionProvider interface.
Sherpa-ONNX must be installed separately: pip install sherpa-onnx
"""

import os
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

try:
    import sherpa_onnx

    SHERPA_AVAILABLE = True
except ImportError:
    SHERPA_AVAILABLE = False
    sherpa_onnx = None  # type: ignore[assignment]

from ..transcription_provider import ModelInfo, TranscriptionProvider, TranscriptionResult


class SherpaProvider(TranscriptionProvider):
    """Sherpa-ONNX speech recognition provider."""

    # Available Sherpa-ONNX models with metadata
    MODELS: dict[str, dict[str, Any]] = {
        "sherpa-zipformer-en-2023-06-26": {
            "name": "Zipformer EN 2023-06-26",
            "size_mb": 70,
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2",
            "type": "zipformer",
        },
        "sherpa-zipformer-en-2023-06-21": {
            "name": "Zipformer EN 2023-06-21",
            "size_mb": 70,
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-21.tar.bz2",
            "type": "zipformer",
        },
        "sherpa-zipformer-en-2023-02-21": {
            "name": "Zipformer EN 2023-02-21",
            "size_mb": 70,
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-02-21.tar.bz2",
            "type": "zipformer",
        },
        "sherpa-zipformer-en-20M-2023-02-17": {
            "name": "Zipformer EN 20M (Small)",
            "size_mb": 30,
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17.tar.bz2",
            "type": "zipformer",
        },
        "sherpa-lstm-en-2023-02-17": {
            "name": "LSTM EN 2023-02-17",
            "size_mb": 50,
            "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-lstm-en-2023-02-17.tar.bz2",
            "type": "lstm",
        },
    }

    sample_rate: int
    model_id: str
    model_path: str
    recognizer: Any  # sherpa_onnx.OnlineRecognizer
    stream: Any  # sherpa_onnx.OnlineStream

    def __init__(self, model_id: str, sample_rate: int = 16000) -> None:
        """
        Initialize the Sherpa-ONNX provider.

        Args:
            model_id: Model identifier (e.g., "sherpa-zipformer-en-2023-06-26")
            sample_rate: Audio sample rate (must match audio capture)

        Raises:
            RuntimeError: If sherpa-onnx is not installed or model not found
        """
        if not SHERPA_AVAILABLE:
            raise RuntimeError(
                "sherpa-onnx package not installed. "
                "Install with: pip install sherpa-onnx"
            )

        self.sample_rate = sample_rate
        self.model_id = model_id
        self.model_path = self._get_model_path(model_id)

        print(f"Loading Sherpa-ONNX model from: {self.model_path}")
        if not os.path.exists(self.model_path):
            raise RuntimeError(
                f"Sherpa model not found at {self.model_path}. "
                f"Please download it with: autocue --download-model {model_id}"
            )

        # Create recognizer based on model type
        self.recognizer = self._create_recognizer()
        self.stream = self.recognizer.create_stream()

    def process_audio(self, audio_data: bytes) -> TranscriptionResult | None:
        """
        Process an audio chunk and return transcription result.

        Args:
            audio_data: Raw audio bytes (16-bit PCM, mono)

        Returns:
            TranscriptionResult with partial or final text, or None if no speech
        """
        # Convert bytes to float32 samples (-1.0 to 1.0)

        samples = np.frombuffer(audio_data, dtype=np.int16).astype(
            np.float32) / 32768.0

        # Feed audio to stream
        self.stream.accept_waveform(self.sample_rate, samples)

        # Decode if ready
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)

        # Get current result
        result = self.recognizer.get_result(self.stream)

        # Handle both API versions: result may be a string or an object with .text
        text = result if isinstance(result, str) else result.text

        if text:
            # Sherpa doesn't have explicit partial/final distinction in the stream API
            # process_audio() always returns partial results (continuous streaming)
            # Only get_final() returns final results
            return TranscriptionResult(text, is_partial=False)

        return None

    def reset(self) -> None:
        """Reset the recognizer state (e.g., after a long pause)."""
        # Create a new stream to reset state
        self.stream = self.recognizer.create_stream()

    def get_final(self) -> TranscriptionResult | None:
        """Get any remaining buffered speech as final result."""
        # Decode any remaining audio
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)

        result = self.recognizer.get_result(self.stream)

        # Handle both API versions: result may be a string or an object with .text
        text = result if isinstance(result, str) else result.text

        if text:
            return TranscriptionResult(text, is_partial=False)
        return None

    @staticmethod
    def get_available_models() -> list[ModelInfo]:
        """Get list of available Sherpa-ONNX models."""
        # Always return the model list, even if sherpa-onnx isn't installed
        # This allows users to see what's available before installing
        return [
            ModelInfo(
                id=model_id,
                name=info["name"],
                provider="sherpa",
                size_mb=info["size_mb"],
                description=f"Sherpa-ONNX {info['type']} model - requires: pip install sherpa-onnx" if not SHERPA_AVAILABLE else f"Sherpa-ONNX {info['type']} model",
            )
            for model_id, info in SherpaProvider.MODELS.items()
        ]

    @staticmethod
    def download_model(
        model_id: str,
        target_dir: str | None = None,
        progress_callback: Callable[[str, int], None] | None = None
    ) -> str:
        """
        Download a Sherpa-ONNX model.

        Args:
            model_id: Model identifier (e.g., "sherpa-zipformer-en-2023-06-26")
            target_dir: Directory to save the model, or None for default
            progress_callback: Optional callback(stage, percent) for progress updates

        Returns:
            Path to the downloaded model as a string.

        Raises:
            ValueError: If model_id is not recognized
        """
        model_info: dict[str, Any] | None = SherpaProvider.MODELS.get(model_id)
        if not model_info:
            raise ValueError(
                f"Unknown Sherpa model: {model_id}. "
                f"Choose from: {list(SherpaProvider.MODELS.keys())}"
            )

        if target_dir is None:
            target_path: Path = Path.home() / ".cache" / "autocue" / "models" / "sherpa"
        else:
            target_path: Path = Path(target_dir)

        target_path.mkdir(parents=True, exist_ok=True)
        model_path: Path = target_path / model_id

        if model_path.exists():
            print(f"Model already exists at {model_path}")
            if progress_callback:
                progress_callback("complete", 100)
            return str(model_path)

        url: str = model_info["url"]
        print(f"Downloading {model_id} from {url}...")
        print("This may take a few minutes depending on your connection.")

        # Download and extract
        # Create temp file and get its name, then close it before extraction
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=False) as tmp:
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

            with tarfile.open(tmp_path, "r:bz2") as tar:
                tar.extractall(target_path)

            if progress_callback:
                progress_callback("extracting", 100)

            # The extracted directory name from the archive might not match model_id
            # Find the extracted directory and rename it if needed
            extracted_dirs = [d for d in target_path.iterdir(
            ) if d.is_dir() and d.name.startswith("sherpa")]
            if extracted_dirs:
                extracted_dir = extracted_dirs[0]
                if extracted_dir.name != model_id:
                    # Rename to match model_id for consistent caching
                    print(f"Renaming {extracted_dir.name} to {model_id}")
                    extracted_dir.rename(model_path)

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
        cache_dir: Path = Path.home() / ".cache" / "autocue" / "models" / "sherpa"
        model_info = self.MODELS.get(model_id)
        if not model_info:
            # Assume custom model path
            return model_id

        model_path = cache_dir / model_id
        # Check if correctly-named directory exists
        if model_path.exists():
            return str(model_path)

        # Fallback: check for legacy extracted directory names (before rename fix)
        # Archives extract as "sherpa-onnx-streaming-*" but model_id is "sherpa-*"
        if cache_dir.exists():
            for dir_path in cache_dir.iterdir():
                if dir_path.is_dir() and model_id in dir_path.name:
                    # Found a likely match - use it (could rename, but is_model_downloaded handles that)
                    return str(dir_path)

        return str(model_path)

    def _find_model_file(self, model_dir: Path, prefix: str, suffix: str) -> Path | None:
        """
        Find a model file matching a prefix and suffix pattern.

        Different Sherpa models use different naming conventions:
        - "encoder-epoch-99-avg-1.onnx"
        - "encoder-epoch-99-avg-1-chunk-16-left-128.onnx"

        Args:
            model_dir: Directory containing model files
            prefix: File prefix to match (e.g., "encoder-epoch-99-avg-1")
            suffix: File suffix to match (e.g., ".onnx")

        Returns:
            Path to the matching file, or None if not found
        """
        # First try exact match
        exact_path = model_dir / f"{prefix}{suffix}"
        if exact_path.exists():
            return exact_path

        # Then try pattern match (prefix-*suffix, excluding .int8.onnx variants)
        for file_path in model_dir.glob(f"{prefix}*{suffix}"):
            # Skip int8 quantized versions - prefer full precision
            if ".int8" not in file_path.name:
                return file_path

        return None

    def _create_recognizer(self) -> Any:
        """
        Create a Sherpa-ONNX recognizer based on model type.

        Returns:
            sherpa_onnx.OnlineRecognizer instance
        """
        assert SHERPA_AVAILABLE and sherpa_onnx is not None

        model_info = self.MODELS.get(self.model_id)
        model_type = model_info["type"] if model_info else "zipformer"

        # Build paths to model files
        model_dir = Path(self.model_path)

        if model_type in ["zipformer", "lstm"]:
            # Transducer models (both Zipformer and LSTM use transducer architecture)
            tokens_path = model_dir / "tokens.txt"

            # Find model files - they may have different naming conventions
            # (e.g., "encoder-epoch-99-avg-1.onnx" or "encoder-epoch-99-avg-1-chunk-16-left-128.onnx")
            encoder_path = self._find_model_file(
                model_dir, "encoder-epoch-99-avg-1", ".onnx")
            decoder_path = self._find_model_file(
                model_dir, "decoder-epoch-99-avg-1", ".onnx")
            joiner_path = self._find_model_file(
                model_dir, "joiner-epoch-99-avg-1", ".onnx")

            # Check if all required files were found
            if not tokens_path.exists():
                raise RuntimeError(
                    f"Required model file not found: {tokens_path}"
                )
            if not encoder_path or not decoder_path or not joiner_path:
                raise RuntimeError(
                    f"Required model files not found in {model_dir}. "
                    f"Expected: tokens.txt, encoder-epoch-99-avg-1*.onnx, "
                    f"decoder-epoch-99-avg-1*.onnx, joiner-epoch-99-avg-1*.onnx"
                )

            # Create recognizer using the factory method
            return sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=str(tokens_path),
                encoder=str(encoder_path),
                decoder=str(decoder_path),
                joiner=str(joiner_path),
                num_threads=2,
                sample_rate=self.sample_rate,
                feature_dim=80,
                decoding_method="greedy_search",
                max_active_paths=4,
                enable_endpoint_detection=True,
                provider="cpu"
            )

        else:
            raise ValueError(f"Unknown model type: {model_type}")
