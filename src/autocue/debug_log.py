"""
Debug logging for tracking position mismatches between server and frontend.

Creates two log files:
- server_words.log: Words detected by the server with their positions
- frontend_words.log: Words highlighted by the frontend with their positions

Logging is disabled by default. Call enable() to turn it on.
"""

from datetime import datetime
from pathlib import Path
from typing import List

# Log files location (in project root)
LOG_DIR: Path = Path(__file__).parent.parent.parent / "logs"
SERVER_LOG: Path = LOG_DIR / "server_words.log"
FRONTEND_LOG: Path = LOG_DIR / "frontend_words.log"

# Global flag to control whether debug logging is enabled
_ENABLED: bool = False  # pylint: disable=invalid-name


def enable() -> None:
    """Enable debug logging."""
    global _ENABLED  # pylint: disable=global-statement
    _ENABLED = True


def disable() -> None:
    """Disable debug logging."""
    global _ENABLED  # pylint: disable=global-statement
    _ENABLED = False


def is_enabled() -> bool:
    """Check if debug logging is enabled."""
    return _ENABLED


def _ensure_log_dir() -> None:
    """Create log directory if it doesn't exist."""
    LOG_DIR.mkdir(exist_ok=True)


def _timestamp() -> str:
    """Get current timestamp."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def clear_logs() -> None:
    """Clear both log files for a fresh session."""
    if not _ENABLED:
        return
    _ensure_log_dir()
    log_file: Path
    for log_file in [SERVER_LOG, FRONTEND_LOG]:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(
                f"=== New session started at {datetime.now().isoformat()} ===\n\n")


def log_server_word(word_index: int, word: str, event: str = "match") -> None:
    """
    Log a word detection on the server side.

    Args:
        word_index: The position in the script
        word: The actual word at that position
        event: Type of event (match, skip, backtrack, forward_jump, validation)
    """
    if not _ENABLED:
        return
    _ensure_log_dir()
    with open(SERVER_LOG, 'a', encoding='utf-8') as f:
        f.write(
            f"[{_timestamp()}] {event:15} pos={word_index:4d} word=\"{word}\"\n")


def log_server_position_update(
    old_pos: int,
    new_pos: int,
    words_in_range: List[str],
    reason: str
) -> None:
    """
    Log a position change on the server side.

    Args:
        old_pos: Previous position
        new_pos: New position
        words_in_range: The words between old and new positions
        reason: Why the position changed
    """
    if not _ENABLED:
        return
    _ensure_log_dir()
    with open(SERVER_LOG, 'a', encoding='utf-8') as f:
        f.write(
            f"[{_timestamp()}] POSITION CHANGE: {old_pos} -> {new_pos} ({reason})\n")
        f.write(f"                 words: {words_in_range}\n")


def log_server_transcript(transcript: str, new_words: List[str]) -> None:
    """Log the transcript and extracted new words."""
    if not _ENABLED:
        return
    _ensure_log_dir()
    with open(SERVER_LOG, 'a', encoding='utf-8') as f:
        f.write(
            f"[{_timestamp()}] transcript: \"{transcript[-60:]}\" new_words={new_words}\n")


def log_frontend_word(
    word_index: int,
    word: str,
    source_line: int = -1,
    source_offset: int = -1
) -> None:
    """
    Log a word highlight on the frontend side.

    Args:
        word_index: The position the frontend computed
        word: The actual word being highlighted
        source_line: The lineIndex received from server
        source_offset: The wordOffset received from server
    """
    if not _ENABLED:
        return
    _ensure_log_dir()
    with open(FRONTEND_LOG, 'a', encoding='utf-8') as f:
        f.write(
            f"[{_timestamp()}] highlight pos={word_index:4d} word=\"{word}\" "
            f"(from line={source_line}, offset={source_offset})\n"
        )


def log_frontend_server_data(word_index: int, line_index: int, word_offset: int) -> None:
    """Log the raw data received from server."""
    if not _ENABLED:
        return
    _ensure_log_dir()
    with open(FRONTEND_LOG, 'a', encoding='utf-8') as f:
        f.write(
            f"[{_timestamp()}] received: wordIndex={word_index}, "
            f"lineIndex={line_index}, wordOffset={word_offset}\n"
        )
