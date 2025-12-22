# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Transcription provider factory and registry.

This module provides a factory pattern for creating transcription providers
and managing the registry of available providers.
"""

from collections.abc import Callable
from pathlib import Path

from ..transcription_provider import ModelInfo, TranscriptionProvider
from .vosk_provider import VoskProvider

# Try to import Sherpa provider
try:
    from .sherpa_provider import SherpaProvider

    SHERPA_AVAILABLE = True
except ImportError:
    SHERPA_AVAILABLE = False
    SherpaProvider = None  # type: ignore[assignment, misc]

# Registry of available providers
PROVIDER_REGISTRY: dict[str, type[TranscriptionProvider]] = {
    "vosk": VoskProvider,
}

if SHERPA_AVAILABLE:
    PROVIDER_REGISTRY["sherpa"] = SherpaProvider  # type: ignore[dict-item]


def create_provider(
    provider_name: str, model_id: str, sample_rate: int = 16000
) -> TranscriptionProvider:
    """
    Factory function to create a transcription provider.

    Args:
        provider_name: Name of the provider ("vosk", "sherpa", etc.)
        model_id: Model identifier to use
        sample_rate: Audio sample rate in Hz (default: 16000)

    Returns:
        Initialized transcription provider instance

    Raises:
        ValueError: If provider_name is not registered
    """
    provider_class = PROVIDER_REGISTRY.get(provider_name)
    if not provider_class:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Unknown provider: {provider_name}. " f"Available providers: {available}"
        )

    return provider_class(model_id, sample_rate)


def get_all_available_models() -> list[ModelInfo]:
    """
    Get all available models from all registered providers.

    Returns:
        List of ModelInfo objects from all providers
    """
    models: list[ModelInfo] = []
    for provider_class in PROVIDER_REGISTRY.values():
        models.extend(provider_class.get_available_models())
    return models


def get_provider_models(provider_name: str) -> list[ModelInfo]:
    """
    Get available models for a specific provider.

    Args:
        provider_name: Name of the provider

    Returns:
        List of ModelInfo objects for the provider, or empty list if not found
    """
    provider_class = PROVIDER_REGISTRY.get(provider_name)
    if not provider_class:
        return []
    return provider_class.get_available_models()


def is_model_downloaded(provider_name: str, model_id: str) -> bool:
    """
    Check if a model is already downloaded.

    Args:
        provider_name: Name of the provider ("vosk", "sherpa")
        model_id: Model identifier

    Returns:
        True if the model is downloaded, False otherwise
    """
    if provider_name == "vosk":
        model_info = VoskProvider.MODELS.get(model_id)
        if not model_info:
            return False
        cache_dir = Path.home() / ".cache" / "autocue" / "models"
        model_path = cache_dir / model_info["dir"]
        return model_path.exists()
    elif provider_name == "sherpa":
        # Check if model is downloaded even if sherpa-onnx isn't installed
        # This allows checking cache without requiring the library
        cache_dir = Path.home() / ".cache" / "autocue" / "models" / "sherpa"
        model_path = cache_dir / model_id
        if model_path.exists():
            return True
        # Fallback: check for old extracted directory names (before rename fix)
        # Archives extract as "sherpa-onnx-streaming-*" but model_id is "sherpa-*"
        if cache_dir.exists():
            for dir_path in cache_dir.iterdir():
                if dir_path.is_dir() and model_id in dir_path.name:
                    # Found a likely match - rename it to the correct name
                    try:
                        dir_path.rename(model_path)
                        print(f"Renamed legacy model directory {dir_path.name} to {model_id}")
                        return True
                    except OSError:
                        # If rename fails, still consider it downloaded
                        return True
        return False
    return False


def download_model_with_progress(
    provider_name: str,
    model_id: str,
    progress_callback: Callable[[str, int], None] | None = None
) -> str:
    """
    Download a model with progress tracking.

    Args:
        provider_name: Name of the provider ("vosk", "sherpa")
        model_id: Model identifier
        progress_callback: Optional callback(stage, percent) for progress updates

    Returns:
        Path to the downloaded model

    Raises:
        ValueError: If provider or model is not recognized
    """
    provider_class = PROVIDER_REGISTRY.get(provider_name)
    if not provider_class:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Unknown provider: {provider_name}. Available providers: {available}"
        )

    return provider_class.download_model(model_id, progress_callback=progress_callback)


__all__ = [
    "create_provider",
    "get_all_available_models",
    "get_provider_models",
    "is_model_downloaded",
    "download_model_with_progress",
    "PROVIDER_REGISTRY",
    "VoskProvider",
]

if SHERPA_AVAILABLE:
    __all__.append("SherpaProvider")
