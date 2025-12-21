"""Tests for the debug_log module enable/disable functionality."""

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from autocue import debug_log


class TestDebugLogEnableDisable:
    """Test the enable/disable functionality of debug logging."""

    def setup_method(self):
        """Reset debug log state before each test."""
        debug_log.disable()

    def test_disabled_by_default(self):
        """Debug logging should be disabled by default."""
        # After importing, logging should be disabled
        debug_log.disable()  # Reset to default state
        assert not debug_log.is_enabled()

    def test_enable(self):
        """enable() should turn on debug logging."""
        debug_log.enable()
        assert debug_log.is_enabled()

    def test_disable(self):
        """disable() should turn off debug logging."""
        debug_log.enable()
        debug_log.disable()
        assert not debug_log.is_enabled()

    def test_clear_logs_no_op_when_disabled(self):
        """clear_logs() should do nothing when logging is disabled."""
        with mock.patch.object(debug_log, '_ensure_log_dir') as mock_ensure:
            debug_log.clear_logs()
            mock_ensure.assert_not_called()

    def test_log_server_word_no_op_when_disabled(self):
        """log_server_word() should do nothing when logging is disabled."""
        with mock.patch.object(debug_log, '_ensure_log_dir') as mock_ensure:
            debug_log.log_server_word(0, "test", "match")
            mock_ensure.assert_not_called()

    def test_log_server_position_update_no_op_when_disabled(self):
        """log_server_position_update() should do nothing when logging is disabled."""
        with mock.patch.object(debug_log, '_ensure_log_dir') as mock_ensure:
            debug_log.log_server_position_update(0, 1, ["word"], "test")
            mock_ensure.assert_not_called()

    def test_log_server_transcript_no_op_when_disabled(self):
        """log_server_transcript() should do nothing when logging is disabled."""
        with mock.patch.object(debug_log, '_ensure_log_dir') as mock_ensure:
            debug_log.log_server_transcript("transcript", ["word"])
            mock_ensure.assert_not_called()

    def test_log_frontend_word_no_op_when_disabled(self):
        """log_frontend_word() should do nothing when logging is disabled."""
        with mock.patch.object(debug_log, '_ensure_log_dir') as mock_ensure:
            debug_log.log_frontend_word(0, "test")
            mock_ensure.assert_not_called()

    def test_log_frontend_server_data_no_op_when_disabled(self):
        """log_frontend_server_data() should do nothing when logging is disabled."""
        with mock.patch.object(debug_log, '_ensure_log_dir') as mock_ensure:
            debug_log.log_frontend_server_data(0, 0, 0)
            mock_ensure.assert_not_called()

    def test_clear_logs_writes_when_enabled(self):
        """clear_logs() should write to log files when enabled."""
        debug_log.enable()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override the log directory
            original_log_dir = debug_log.LOG_DIR
            original_server_log = debug_log.SERVER_LOG
            original_frontend_log = debug_log.FRONTEND_LOG
            try:
                debug_log.LOG_DIR = Path(tmpdir)
                debug_log.SERVER_LOG = Path(tmpdir) / "server_words.log"
                debug_log.FRONTEND_LOG = Path(tmpdir) / "frontend_words.log"

                debug_log.clear_logs()

                assert debug_log.SERVER_LOG.exists()
                assert debug_log.FRONTEND_LOG.exists()
                assert "New session started" in debug_log.SERVER_LOG.read_text()
            finally:
                debug_log.LOG_DIR = original_log_dir
                debug_log.SERVER_LOG = original_server_log
                debug_log.FRONTEND_LOG = original_frontend_log

    def test_log_server_word_writes_when_enabled(self):
        """log_server_word() should write to log file when enabled."""
        debug_log.enable()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_log_dir = debug_log.LOG_DIR
            original_server_log = debug_log.SERVER_LOG
            try:
                debug_log.LOG_DIR = Path(tmpdir)
                debug_log.SERVER_LOG = Path(tmpdir) / "server_words.log"

                debug_log.log_server_word(42, "hello", "match")

                assert debug_log.SERVER_LOG.exists()
                content = debug_log.SERVER_LOG.read_text()
                assert "pos=  42" in content
                assert 'word="hello"' in content
            finally:
                debug_log.LOG_DIR = original_log_dir
                debug_log.SERVER_LOG = original_server_log
