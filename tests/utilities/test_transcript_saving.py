"""Tests for the transcript saving functionality."""

import asyncio
import tempfile
from pathlib import Path
from typing import Generator
from unittest import mock

import pytest

from autocue.main import AutocueApp, TRANSCRIPT_DIR


class TestTranscriptSaving:
    """Test the transcript saving functionality."""

    def test_transcript_disabled_by_default(self) -> None:
        """Transcript saving should be disabled by default."""
        app: AutocueApp = AutocueApp()
        assert not app.save_transcript
        assert app.transcript_file is None

    def test_transcript_enabled_via_parameter(self) -> None:
        """Transcript saving can be enabled via constructor parameter."""
        app: AutocueApp = AutocueApp(save_transcript=True)
        assert app.save_transcript
        # File not created until _start_transcript is called
        assert app.transcript_file is None

    def test_write_transcript_no_op_when_disabled(self) -> None:
        """_write_transcript() should do nothing when saving is disabled."""
        app: AutocueApp = AutocueApp(save_transcript=False)
        # Should not raise even without transcript file
        app._write_transcript("test text", is_partial=False)

    def test_write_transcript_no_op_without_file(self) -> None:
        """_write_transcript() should do nothing without transcript file."""
        app: AutocueApp = AutocueApp(save_transcript=True)
        # File not initialized
        app._write_transcript("test text", is_partial=False)
        # Should not raise


class TestDynamicTranscriptControl:
    """Test the dynamic start/stop transcript functionality."""

    @pytest.fixture
    def mock_server(self) -> Generator[mock.AsyncMock, None, None]:
        """Create a mock server for testing."""
        server: mock.AsyncMock = mock.AsyncMock()
        server.send_transcript_status = mock.AsyncMock()
        yield server

    @pytest.mark.asyncio
    async def test_start_transcript_creates_file(self, mock_server: mock.AsyncMock) -> None:
        """_start_transcript() should create a new transcript file."""
        app: AutocueApp = AutocueApp(save_transcript=False)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path: Path = Path(tmpdir)
            with mock.patch('autocue.main.TRANSCRIPT_DIR', tmpdir_path):
                await app._start_transcript()

                assert app.save_transcript is True
                assert app.transcript_file is not None
                assert app.transcript_file.exists()
                mock_server.send_transcript_status.assert_called_once()
                call_args = mock_server.send_transcript_status.call_args
                assert call_args[0][0] is True  # recording=True

    @pytest.mark.asyncio
    async def test_start_transcript_no_op_if_already_recording(self, mock_server: mock.AsyncMock) -> None:
        """_start_transcript() should be a no-op if already recording."""
        app: AutocueApp = AutocueApp(save_transcript=True)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path: Path = Path(tmpdir)
            with mock.patch('autocue.main.TRANSCRIPT_DIR', tmpdir_path):
                # Start first time
                await app._start_transcript()
                first_file: Path | None = app.transcript_file

                # Reset mock
                mock_server.send_transcript_status.reset_mock()

                # Start again - should use same file
                await app._start_transcript()
                assert app.transcript_file == first_file
                # Should still send status update
                mock_server.send_transcript_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_transcript_closes_file(self, mock_server: mock.AsyncMock) -> None:
        """_stop_transcript() should close the transcript and clear state."""
        app: AutocueApp = AutocueApp(save_transcript=False)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path: Path = Path(tmpdir)
            with mock.patch('autocue.main.TRANSCRIPT_DIR', tmpdir_path):
                # Start recording
                await app._start_transcript()
                transcript_file: Path | None = app.transcript_file

                # Stop recording
                await app._stop_transcript()

                assert app.save_transcript is False
                assert app.transcript_file is None

                # File should have end marker
                assert transcript_file is not None, "File should have been created"
                content: str = transcript_file.read_text()
                assert "Transcript ended" in content

                # Should send status update
                call_args = mock_server.send_transcript_status.call_args
                assert call_args[0][0] is False  # recording=False

    @pytest.mark.asyncio
    async def test_stop_transcript_no_op_if_not_recording(self, mock_server: mock.AsyncMock) -> None:
        """_stop_transcript() should be a no-op if not recording."""
        app: AutocueApp = AutocueApp(save_transcript=False)
        app.server = mock_server

        await app._stop_transcript()

        assert app.save_transcript is False
        assert app.transcript_file is None
        mock_server.send_transcript_status.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_start_stop_cycle(self, mock_server: mock.AsyncMock) -> None:
        """Test starting and stopping transcript multiple times."""
        app: AutocueApp = AutocueApp(save_transcript=False)
        app.server = mock_server

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path: Path = Path(tmpdir)
            with mock.patch('autocue.main.TRANSCRIPT_DIR', tmpdir_path):
                # First cycle
                await app._start_transcript()
                first_file: Path | None = app.transcript_file
                app._write_transcript("first recording", is_partial=False)
                await app._stop_transcript()

                # Wait a moment to ensure different timestamp
                await asyncio.sleep(1.1)

                # Second cycle
                await app._start_transcript()
                second_file: Path | None = app.transcript_file
                app._write_transcript("second recording", is_partial=False)
                await app._stop_transcript()

                # Files should be different (different timestamps)
                assert first_file is not None, "First file should have been created"
                assert second_file is not None, "Second file should have been created"
                assert first_file != second_file
                assert first_file.exists()
                assert second_file.exists()

                # Content should be correct
                first_content: str = first_file.read_text()
                second_content: str = second_file.read_text()
                assert "first recording" in first_content
                assert "second recording" in second_content
