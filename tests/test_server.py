# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Tests for WebServer functionality, including scripts_folder support.
"""

import tempfile
from pathlib import Path

from autocue.server import WebServer


def test_get_sample_scripts_without_extras():
    """Test _get_sample_scripts returns grouped format with only samples."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()

        # Create sample script files
        (samples_dir / "test_script.md").write_text("# Test Script")
        (samples_dir / "another_script.md").write_text("# Another Script")

        server = WebServer(samples_dir=str(samples_dir))
        scripts = server._get_sample_scripts()

        # Verify grouped format
        assert "samples" in scripts
        assert "extras" in scripts
        assert len(scripts["samples"]) == 2
        assert len(scripts["extras"]) == 0

        # Verify sample script details
        assert scripts["samples"][0]["name"] == "Another Script"
        assert scripts["samples"][0]["filename"] == "another_script.md"
        assert scripts["samples"][0]["source"] == "samples"


def test_get_sample_scripts_with_extras():
    """Test _get_sample_scripts returns both samples and extras."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()
        scripts_folder = Path(tmpdir) / "my_scripts"
        scripts_folder.mkdir()

        # Create sample script files
        (samples_dir / "sample.md").write_text("# Sample")

        # Create extra script files
        (scripts_folder / "my_video.md").write_text("# My Video")
        (scripts_folder / "tutorial.md").write_text("# Tutorial")

        server = WebServer(
            samples_dir=str(samples_dir),
            scripts_folder=str(scripts_folder)
        )
        scripts = server._get_sample_scripts()

        # Verify both groups exist
        assert len(scripts["samples"]) == 1
        assert len(scripts["extras"]) == 2

        # Verify extra script details
        assert scripts["extras"][0]["name"] == "My Video"
        assert scripts["extras"][0]["filename"] == "my_video.md"
        assert scripts["extras"][0]["source"] == "extras"


def test_get_sample_scripts_nonexistent_folders():
    """Test _get_sample_scripts handles nonexistent folders gracefully."""
    server = WebServer(
        samples_dir="/nonexistent/samples",
        scripts_folder="/nonexistent/scripts"
    )
    scripts = server._get_sample_scripts()

    # Should return empty groups
    assert len(scripts["samples"]) == 0
    assert len(scripts["extras"]) == 0


def test_load_sample_script_from_samples():
    """Test _load_sample_script loads from samples directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()

        # Create sample script
        script_content = "# Test Script\n\nThis is a test."
        (samples_dir / "test.md").write_text(script_content)

        server = WebServer(samples_dir=str(samples_dir))
        content = server._load_sample_script("test.md", "samples")

        assert content == script_content


def test_load_sample_script_from_extras():
    """Test _load_sample_script loads from extras directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()
        scripts_folder = Path(tmpdir) / "scripts"
        scripts_folder.mkdir()

        # Create extra script
        script_content = "# My Script\n\nMy content."
        (scripts_folder / "myscript.md").write_text(script_content)

        server = WebServer(
            samples_dir=str(samples_dir),
            scripts_folder=str(scripts_folder)
        )
        content = server._load_sample_script("myscript.md", "extras")

        assert content == script_content


def test_load_sample_script_prevents_path_traversal():
    """Test _load_sample_script sanitizes filenames to prevent path traversal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()

        # Create a script outside the samples directory
        secret_file = Path(tmpdir) / "secret.md"
        secret_file.write_text("Secret content")

        server = WebServer(samples_dir=str(samples_dir))

        # Try to access file outside samples dir using path traversal
        content = server._load_sample_script("../secret.md", "samples")

        # Should fail (return None) because file is outside samples dir
        assert content is None


def test_load_sample_script_only_accepts_markdown():
    """Test _load_sample_script only loads .md files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()

        # Create a non-markdown file
        (samples_dir / "script.txt").write_text("Not markdown")

        server = WebServer(samples_dir=str(samples_dir))
        content = server._load_sample_script("script.txt", "samples")

        # Should return None for non-.md files
        assert content is None


def test_get_sample_scripts_refreshes_from_disk():
    """Test _get_sample_scripts reads fresh data from disk each time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()

        # Create initial script
        (samples_dir / "initial.md").write_text("# Initial")

        server = WebServer(samples_dir=str(samples_dir))

        # First call
        scripts1 = server._get_sample_scripts()
        assert len(scripts1["samples"]) == 1
        assert scripts1["samples"][0]["filename"] == "initial.md"

        # Add a new script file
        (samples_dir / "new.md").write_text("# New")

        # Second call should see the new file
        scripts2 = server._get_sample_scripts()
        assert len(scripts2["samples"]) == 2
        filenames = [s["filename"] for s in scripts2["samples"]]
        assert "initial.md" in filenames
        assert "new.md" in filenames


def test_get_sample_scripts_extras_from_subdirectories():
    """Test _get_sample_scripts discovers scripts in subdirectories of the extras folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()
        scripts_folder = Path(tmpdir) / "my_scripts"
        scripts_folder.mkdir()

        # Create scripts at root level and in subdirectories
        (scripts_folder / "root_script.md").write_text("# Root Script")
        subdir = scripts_folder / "project_alpha"
        subdir.mkdir()
        (subdir / "intro.md").write_text("# Intro")
        (subdir / "closing.md").write_text("# Closing")

        server = WebServer(
            samples_dir=str(samples_dir),
            scripts_folder=str(scripts_folder)
        )
        scripts = server._get_sample_scripts()

        assert len(scripts["extras"]) == 3
        names = {s["name"] for s in scripts["extras"]}
        assert "Root Script" in names
        assert "Project Alpha / Intro" in names
        assert "Project Alpha / Closing" in names

        # Verify filenames use forward-slash relative paths
        filenames = {s["filename"] for s in scripts["extras"]}
        assert "root_script.md" in filenames
        assert "project_alpha/intro.md" in filenames
        assert "project_alpha/closing.md" in filenames


def test_get_sample_scripts_nested_subdirectories():
    """Test _get_sample_scripts handles deeply nested subdirectories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()
        scripts_folder = Path(tmpdir) / "my_scripts"
        scripts_folder.mkdir()

        # Create a deeply nested script
        nested = scripts_folder / "season_one" / "episode_two"
        nested.mkdir(parents=True)
        (nested / "scene_three.md").write_text("# Scene Three")

        server = WebServer(
            samples_dir=str(samples_dir),
            scripts_folder=str(scripts_folder)
        )
        scripts = server._get_sample_scripts()

        assert len(scripts["extras"]) == 1
        entry = scripts["extras"][0]
        assert entry["name"] == "Season One / Episode Two / Scene Three"
        assert entry["filename"] == "season_one/episode_two/scene_three.md"


def test_load_sample_script_from_subdirectory():
    """Test _load_sample_script loads scripts from subdirectories of extras folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()
        scripts_folder = Path(tmpdir) / "scripts"
        scripts_folder.mkdir()

        # Create script in a subdirectory
        subdir = scripts_folder / "project"
        subdir.mkdir()
        script_content = "# Project Script\n\nContent here."
        (subdir / "draft.md").write_text(script_content)

        server = WebServer(
            samples_dir=str(samples_dir),
            scripts_folder=str(scripts_folder)
        )
        content = server._load_sample_script("project/draft.md", "extras")

        assert content == script_content


def test_load_sample_script_subdirectory_prevents_path_traversal():
    """Test _load_sample_script prevents path traversal via subdirectory paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()
        scripts_folder = Path(tmpdir) / "scripts"
        scripts_folder.mkdir()

        # Create a file outside the scripts folder
        secret_file = Path(tmpdir) / "secret.md"
        secret_file.write_text("Secret content")

        server = WebServer(
            samples_dir=str(samples_dir),
            scripts_folder=str(scripts_folder)
        )

        # Try various path traversal attempts
        assert server._load_sample_script("../secret.md", "extras") is None
        assert server._load_sample_script("subdir/../../secret.md", "extras") is None


def test_get_sample_scripts_excludes_dot_directories():
    """Test _get_sample_scripts skips subdirectories that start with a period."""
    with tempfile.TemporaryDirectory() as tmpdir:
        samples_dir = Path(tmpdir) / "samples"
        samples_dir.mkdir()
        scripts_folder = Path(tmpdir) / "my_scripts"
        scripts_folder.mkdir()

        # Create a visible script
        (scripts_folder / "visible.md").write_text("# Visible")

        # Create scripts inside hidden directories
        hidden = scripts_folder / ".hidden"
        hidden.mkdir()
        (hidden / "secret.md").write_text("# Secret")

        nested_hidden = scripts_folder / ".drafts" / "wip"
        nested_hidden.mkdir(parents=True)
        (nested_hidden / "draft.md").write_text("# Draft")

        server = WebServer(
            samples_dir=str(samples_dir),
            scripts_folder=str(scripts_folder)
        )
        scripts = server._get_sample_scripts()

        assert len(scripts["extras"]) == 1
        assert scripts["extras"][0]["name"] == "Visible"
