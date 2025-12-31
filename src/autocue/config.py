# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Configuration management for Autocue.
Handles loading and saving settings from a YAML config file.
"""

from pathlib import Path
from typing import Any, TypedDict

import yaml

CONFIG_FILENAME: str = ".autocue.yaml"


class DisplaySettings(TypedDict):
    """Type definition for display configuration settings."""
    fontSize: int
    fontFamily: str
    lineHeight: float
    pastLines: int
    futureLines: int
    theme: str
    highlightColor: str
    textColor: str
    dimColor: str
    backgroundColor: str
    skipHeaders: bool


class TrackingSettings(TypedDict):
    """Type definition for tracking configuration settings."""
    window_size: int
    match_threshold: float
    backtrack_threshold: int
    max_jump_distance: int
    skip_headers: bool


class TranscriptionConfig(TypedDict):
    """Type definition for transcription configuration settings."""
    provider: str  # "vosk" or "sherpa"
    model_id: str  # Model identifier (e.g., "vosk-en-us-small")
    model_path: str | None  # Optional custom path


class Config(TypedDict):
    """Type definition for the complete configuration."""
    # Transcription settings (new)
    transcription: TranscriptionConfig
    # Legacy settings (deprecated but kept for backward compatibility)
    model: str | None
    model_path: str | None
    # Server settings
    host: str
    port: int
    audio_device: int | None
    chunk_ms: int
    # Scripts folder (optional)
    scripts_folder: str | None
    # UI settings
    display: DisplaySettings
    tracking: TrackingSettings


# Default configuration values
DEFAULT_CONFIG: Config = {
    # Transcription settings (new)
    "transcription": {
        "provider": "vosk",
        "model_id": "vosk-en-us-small",
        "model_path": None,
    },

    # Legacy settings (deprecated but kept for backward compatibility)
    "model": None,
    "model_path": None,

    # Server settings
    "host": "127.0.0.1",
    "port": 8000,
    "audio_device": None,
    "chunk_ms": 100,

    # Scripts folder (optional - set to a folder path to show extra scripts in UI)
    "scripts_folder": None,

    # UI display settings
    "display": {
        "fontSize": 48,
        "fontFamily": "Georgia, serif",
        "lineHeight": 1.6,
        "pastLines": 1,
        "futureLines": 8,
        "theme": "dark",
        "highlightColor": "#FFD700",
        "textColor": "#FFFFFF",
        "dimColor": "#666666",
        "backgroundColor": "#1a1a1a",
        "skipHeaders": False,
    },

    # Tracking thresholds
    "tracking": {
        "window_size": 8,
        "match_threshold": 65.0,
        "backtrack_threshold": 3,
        # Max words to jump (prevents jumping to similar text far away)
        "max_jump_distance": 50,
        # Skip headers during tracking (headers still displayed but not tracked)
        "skip_headers": False,
    },
}


def get_config_path() -> Path:
    """Get the path to the config file in the current working directory."""
    return Path.cwd() / CONFIG_FILENAME


def _deep_merge(base, override):
    """
    Deep merge two dictionaries, with override taking precedence.
    Returns a new dictionary without modifying the originals.

    Args:
        base: Base dictionary to merge from.
        override: Dictionary with values that take precedence over base.

    Returns:
        New dictionary with merged values.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate old configuration format to new format.

    Automatically converts old 'model' and 'model_path' fields to new
    'transcription' structure.

    Args:
        config: Configuration dictionary (may be in old or new format)

    Returns:
        Migrated configuration dictionary
    """
    # Check if already using new format
    if "transcription" in config:
        return config

    # Check if old format exists
    if "model" in config or "model_path" in config:
        old_model = config.get("model", "small")
        old_path = config.get("model_path")

        if old_path:
            # Custom path provided
            config["transcription"] = {
                "provider": "vosk",
                "model_id": "custom",
                "model_path": old_path,
            }
        elif old_model:
            # Model name provided - convert to new model_id format
            config["transcription"] = {
                "provider": "vosk",
                "model_id": f"vosk-en-us-{old_model}",
                "model_path": None,
            }
        else:
            # Use default
            config["transcription"] = DEFAULT_CONFIG["transcription"].copy()

        # Clear old fields (but keep them for backward compat in config dict)
        config["model"] = None
        config["model_path"] = None

        print(
            f"Note: Migrated old config format to new transcription format "
            f"(provider={config['transcription']['provider']}, "
            f"model_id={config['transcription']['model_id']})"
        )

    return config


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file, merged with defaults.

    Automatically migrates old configuration format to new format.

    Args:
        config_path: Optional path to config file. If None, uses default location.

    Returns:
        Configuration dictionary with all values (defaults + overrides from file).
    """
    if config_path is None:
        config_path = get_config_path()

    # Start with defaults
    config: dict[str, Any] = _deep_merge({}, DEFAULT_CONFIG)

    # Load from file if it exists
    if config_path.exists():
        try:
            with open(config_path, encoding='utf-8') as f:
                file_config: dict[str, Any] | None = yaml.safe_load(f)
                if file_config:
                    config = _deep_merge(config, file_config)
        except (OSError, yaml.YAMLError) as e:
            print(f"Warning: Could not load config from {config_path}: {e}")

    # Migrate old config format if necessary
    config = migrate_config(config)

    return config  # type: ignore[return-value]


def save_config(config: Config, config_path: Path | None = None) -> bool:
    """
    Save configuration to file.

    Args:
        config: Configuration dictionary to save.
        config_path: Optional path to config file. If None, uses default location.

    Returns:
        True if save was successful, False otherwise.
    """
    if config_path is None:
        config_path = get_config_path()

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return True
    except (OSError, yaml.YAMLError) as e:
        print(f"Error saving config to {config_path}: {e}")
        return False


def get_display_settings(config: Config) -> DisplaySettings:
    """
    Extract display settings from config in the format expected by WebServer.

    Args:
        config: Configuration dictionary.

    Returns:
        Display settings dictionary.
    """
    return config.get("display", DEFAULT_CONFIG["display"]).copy()  # type: ignore[return-value]


def get_tracking_settings(config: Config) -> TrackingSettings:
    """
    Extract tracking settings from config.

    Args:
        config: Configuration dictionary.

    Returns:
        Tracking settings dictionary.
    """
    return config.get("tracking", DEFAULT_CONFIG["tracking"]).copy()  # type: ignore[return-value]


def get_transcription_settings(config: Config) -> TranscriptionConfig:
    """
    Extract transcription settings from config.

    Args:
        config: Configuration dictionary.

    Returns:
        Transcription settings dictionary.
    """
    return config.get("transcription",
                      DEFAULT_CONFIG["transcription"]
                      ).copy()  # type: ignore[return-value]


def update_config_display(config: Config, display_settings: DisplaySettings) -> Config:
    """
    Update the display section of the config with new settings.
    Returns a new config dict.

    Args:
        config: Current configuration.
        display_settings: New display settings to merge in.

    Returns:
        New configuration with updated display settings.
    """
    new_config: dict[str, Any] = _deep_merge({}, config)
    new_config["display"] = _deep_merge(
        new_config.get("display", {}),
        display_settings
    )
    return new_config  # type: ignore[return-value]
