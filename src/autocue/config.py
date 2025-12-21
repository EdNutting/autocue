"""
Configuration management for Autocue.
Handles loading and saving settings from a YAML config file.
"""

from pathlib import Path
from typing import Optional

import yaml


CONFIG_FILENAME = ".autocue.yaml"

# Default configuration values
DEFAULT_CONFIG = {
    # CLI defaults
    "model": "small",
    "model_path": None,
    "host": "127.0.0.1",
    "port": 8000,
    "audio_device": None,
    "chunk_ms": 100,

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
    },

    # Tracking thresholds
    "tracking": {
        "window_size": 8,
        "match_threshold": 65.0,
        "backtrack_threshold": 3,
        # Max words to jump (prevents jumping to similar text far away)
        "max_jump_distance": 50,
    },
}


def get_config_path() -> Path:
    """Get the path to the config file in the current working directory."""
    return Path.cwd() / CONFIG_FILENAME


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries, with override taking precedence.
    Returns a new dictionary without modifying the originals.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Optional[Path] = None) -> dict:
    """
    Load configuration from file, merged with defaults.

    Args:
        config_path: Optional path to config file. If None, uses default location.

    Returns:
        Configuration dictionary with all values (defaults + overrides from file).
    """
    if config_path is None:
        config_path = get_config_path()

    # Start with defaults
    config = _deep_merge({}, DEFAULT_CONFIG)

    # Load from file if it exists
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    config = _deep_merge(config, file_config)
        except (OSError, yaml.YAMLError) as e:
            print(f"Warning: Could not load config from {config_path}: {e}")

    return config


def save_config(config: dict, config_path: Optional[Path] = None) -> bool:
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


def get_display_settings(config: dict) -> dict:
    """Extract display settings from config in the format expected by WebServer."""
    return config.get("display", DEFAULT_CONFIG["display"]).copy()


def get_tracking_settings(config: dict) -> dict:
    """Extract tracking settings from config."""
    return config.get("tracking", DEFAULT_CONFIG["tracking"]).copy()


def update_config_display(config: dict, display_settings: dict) -> dict:
    """
    Update the display section of the config with new settings.
    Returns a new config dict.
    """
    new_config = _deep_merge({}, config)
    new_config["display"] = _deep_merge(
        new_config.get("display", {}),
        display_settings
    )
    return new_config
