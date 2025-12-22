# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""Tests for model download caching functionality."""

import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.autocue.providers import is_model_downloaded
from src.autocue.providers.sherpa_provider import SherpaProvider


class TestSherpaModelCaching:
    """Test that Sherpa model caching works correctly."""

    def test_download_model_skips_if_exists(self):
        """Verify that download_model returns early if model already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            model_id = "sherpa-zipformer-en-2023-06-26"
            model_path = cache_dir / model_id
            model_path.mkdir()

            # Mock the download - it shouldn't be called
            with patch('urllib.request.urlretrieve') as mock_retrieve:
                result = SherpaProvider.download_model(model_id, str(cache_dir))

                # Should return the existing path without downloading
                assert result == str(model_path)
                # Verify download was not attempted
                mock_retrieve.assert_not_called()

    def test_download_renames_extracted_directory(self):
        """Verify that download_model renames the extracted directory to match model_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            model_id = "sherpa-zipformer-en-2023-06-26"

            # Create a fake archive with legacy naming
            legacy_name = "sherpa-onnx-streaming-zipformer-en-2023-06-26"
            archive_path = cache_dir / "model.tar.bz2"

            # Create archive with legacy-named directory
            with tarfile.open(archive_path, "w:bz2") as tar:
                legacy_dir = cache_dir / "temp" / legacy_name
                legacy_dir.mkdir(parents=True)
                # Add a dummy file
                dummy_file = legacy_dir / "tokens.txt"
                dummy_file.write_text("test")
                tar.add(legacy_dir, arcname=legacy_name)

            # Mock urlretrieve to return our test archive
            def mock_urlretrieve(url, filename, hook=None):
                # Copy our test archive to the requested location
                with open(archive_path, 'rb') as src, open(filename, 'wb') as dst:
                    dst.write(src.read())
                return filename, None

            with patch('urllib.request.urlretrieve', side_effect=mock_urlretrieve):
                result = SherpaProvider.download_model(model_id, str(cache_dir))

                # Verify the extracted directory was renamed to match model_id
                expected_path = cache_dir / model_id
                assert expected_path.exists(), f"Expected directory {expected_path} doesn't exist"
                assert not (cache_dir / legacy_name).exists(), "Legacy directory should be renamed"
                assert result == str(expected_path)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
