# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Tests for configuration management, including scripts_folder functionality.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from autocue.config import (
    DEFAULT_CONFIG,
    Config,
    load_config,
)


def test_default_config_has_scripts_folder():
    """Verify scripts_folder is in default config."""
    assert "scripts_folder" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["scripts_folder"] is None


def test_load_config_with_scripts_folder():
    """Test loading config with scripts_folder set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / ".autocue.yaml"
        test_scripts_path = Path(tmpdir) / "scripts"
        test_scripts_path.mkdir()

        # Write config with scripts_folder
        config_data = {
            "scripts_folder": str(test_scripts_path),
            "host": "127.0.0.1",
            "port": 8000,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        # Load and verify
        config = load_config(config_path)
        assert config["scripts_folder"] == str(test_scripts_path)


def test_load_config_without_scripts_folder():
    """Test loading config without scripts_folder uses default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / ".autocue.yaml"

        # Write config without scripts_folder
        config_data = {
            "host": "127.0.0.1",
            "port": 8000,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        # Load and verify defaults to None
        config = load_config(config_path)
        assert config["scripts_folder"] is None
