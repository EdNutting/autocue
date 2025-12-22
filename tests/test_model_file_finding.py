"""Tests for Sherpa model file finding logic."""

import tempfile
from pathlib import Path

import pytest

from autocue.providers.sherpa_provider import SherpaProvider


class TestModelFileFinding:
    """Test the _find_model_file method handles different naming conventions."""

    def test_exact_match(self):
        """Test finding a file with exact name match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            # Create exact match file
            (model_dir / "encoder-epoch-99-avg-1.onnx").touch()

            provider = SherpaProvider.__new__(SherpaProvider)
            result = provider._find_model_file(model_dir, "encoder-epoch-99-avg-1", ".onnx")

            assert result is not None
            assert result.name == "encoder-epoch-99-avg-1.onnx"

    def test_pattern_match_with_chunk_info(self):
        """Test finding a file with additional chunk information in name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            # Create file with chunk info (like 2023-06-26 model)
            (model_dir / "encoder-epoch-99-avg-1-chunk-16-left-128.onnx").touch()

            provider = SherpaProvider.__new__(SherpaProvider)
            result = provider._find_model_file(model_dir, "encoder-epoch-99-avg-1", ".onnx")

            assert result is not None
            assert result.name == "encoder-epoch-99-avg-1-chunk-16-left-128.onnx"

    def test_prefers_full_precision_over_int8(self):
        """Test that full precision model is preferred over int8 quantized version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            # Create both int8 and full precision files
            (model_dir / "encoder-epoch-99-avg-1.int8.onnx").touch()
            (model_dir / "encoder-epoch-99-avg-1.onnx").touch()

            provider = SherpaProvider.__new__(SherpaProvider)
            result = provider._find_model_file(model_dir, "encoder-epoch-99-avg-1", ".onnx")

            assert result is not None
            assert ".int8" not in result.name
            assert result.name == "encoder-epoch-99-avg-1.onnx"

    def test_prefers_exact_match_over_pattern(self):
        """Test that exact match is preferred over pattern match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            # Create both exact and pattern match files
            (model_dir / "encoder-epoch-99-avg-1.onnx").touch()
            (model_dir / "encoder-epoch-99-avg-1-chunk-16-left-128.onnx").touch()

            provider = SherpaProvider.__new__(SherpaProvider)
            result = provider._find_model_file(model_dir, "encoder-epoch-99-avg-1", ".onnx")

            assert result is not None
            # Should prefer exact match
            assert result.name == "encoder-epoch-99-avg-1.onnx"

    def test_returns_none_when_not_found(self):
        """Test that None is returned when no matching file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            # Don't create any files

            provider = SherpaProvider.__new__(SherpaProvider)
            result = provider._find_model_file(model_dir, "encoder-epoch-99-avg-1", ".onnx")

            assert result is None

    def test_skips_int8_when_no_full_precision(self):
        """Test that int8 version is used if no full precision version exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            # Only create int8 file
            (model_dir / "encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx").touch()

            provider = SherpaProvider.__new__(SherpaProvider)
            result = provider._find_model_file(model_dir, "encoder-epoch-99-avg-1", ".onnx")

            # Should return None since we skip int8 variants
            assert result is None
