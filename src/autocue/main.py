"""
Main autocue application.
Orchestrates audio capture, transcription, script tracking, and the web UI.
"""

import argparse
import asyncio
import contextlib
import logging
import signal
import time
from datetime import datetime
from pathlib import Path

from . import debug_log
from .audio import AudioCapture, list_devices
from .config import (
    DEFAULT_CONFIG,
    Config,
    DisplaySettings,
    TrackingSettings,
    TranscriptionConfig,
    get_config_path,
    get_display_settings,
    get_tracking_settings,
    load_config,
    save_config,
)
from .providers import get_all_available_models
from .server import WebServer
from .tracker import ScriptTracker
from .transcribe import Transcriber, download_model

logger = logging.getLogger(__name__)


# Transcript files location (in project root)
TRANSCRIPT_DIR = Path(__file__).parent.parent.parent / "transcripts"


class AutocueApp:
    """
    Main autocue application that coordinates all components.
    """

    def __init__(
        self,
        transcription_config: TranscriptionConfig | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        audio_device: int | None = None,
        chunk_ms: int = 100,
        display_settings: DisplaySettings | None = None,
        tracking_settings: TrackingSettings | None = None,
        save_transcript: bool = False
    ) -> None:
        # type: ignore[assignment]
        self.transcription_config: TranscriptionConfig = (
            transcription_config or DEFAULT_CONFIG["transcription"]
        )
        self.host: str = host
        self.port: int = port
        self.audio_device: int | None = audio_device
        self.chunk_ms: int = chunk_ms
        # type: ignore[assignment]
        self.display_settings: DisplaySettings = (
            display_settings or DEFAULT_CONFIG["display"]
        )
        # type: ignore[assignment]
        self.tracking_settings: TrackingSettings = (
            tracking_settings or DEFAULT_CONFIG["tracking"]
        )
        self.save_transcript: bool = save_transcript

        self.audio: AudioCapture | None = None
        self.transcriber: Transcriber | None = None
        self.tracker: ScriptTracker | None = None
        self.server: WebServer | None = None
        self.transcript_file: Path | None = None

        self.running: bool = False

        # Track last sent position to avoid duplicate updates
        self._last_sent_word_index: int | None = None
        self._last_sent_line_index: int | None = None
        self._last_sent_word_offset: int | None = None

    def write_transcript(self, text: str, is_partial: bool) -> None:
        """Write recognized text to the transcript file."""
        if not self.save_transcript or not self.transcript_file:
            return
        # Only write final (non-partial) results to avoid duplicates
        if not is_partial and text.strip():
            with open(self.transcript_file, 'a', encoding='utf-8') as f:
                f.write(f"{text}\n")

    async def start_transcript(self) -> None:
        """Start transcript recording."""
        assert self.server is not None, "Server must be initialized"
        if self.save_transcript and self.transcript_file:
            # Already recording
            await self.server.send_transcript_status(True, str(self.transcript_file))
            return

        self.save_transcript = True
        TRANSCRIPT_DIR.mkdir(exist_ok=True)
        timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.transcript_file = TRANSCRIPT_DIR / f"transcript_{timestamp}.txt"
        with open(self.transcript_file, 'w', encoding='utf-8') as f:
            f.write(
                f"=== Transcript started at {datetime.now().isoformat()} ===\n\n")
        print(f"Transcript recording started: {self.transcript_file}")
        await self.server.send_transcript_status(True, str(self.transcript_file))

    async def stop_transcript(self) -> None:
        """Stop transcript recording."""
        assert self.server is not None, "Server must be initialized"
        if not self.save_transcript:
            # Already stopped
            await self.server.send_transcript_status(False)
            return

        if self.transcript_file:
            with open(self.transcript_file, 'a', encoding='utf-8') as f:
                f.write(
                    f"\n=== Transcript ended at {datetime.now().isoformat()} ===\n")
            print(f"Transcript recording stopped: {self.transcript_file}")

        self.save_transcript = False
        self.transcript_file = None
        await self.server.send_transcript_status(False)

    async def _initialize_audio_and_transcriber(self) -> None:
        """Initialize audio capture and transcriber (called when prompting starts)."""
        assert self.server is not None, "Server must be initialized"

        if self.audio is None:
            print("Initializing audio capture...")
            self.audio = AudioCapture(
                chunk_duration_ms=self.chunk_ms,
                device=self.audio_device
            )
            self.audio.start()

        if self.transcriber is None:
            provider = self.transcription_config['provider']
            model_id = self.transcription_config['model_id']
            print(f"Loading transcription model: {provider} / {model_id}")

            # Notify clients that model is loading
            await self.server.send_model_loading_status("loading", provider, model_id)

            # Run model loading in executor to avoid blocking
            loop = asyncio.get_event_loop()
            self.transcriber = await loop.run_in_executor(
                None,
                lambda: Transcriber(
                    provider=provider,
                    model_id=model_id,
                    model_path=self.transcription_config.get("model_path"),
                )
            )

            # Notify clients that model is ready
            await self.server.send_model_loading_status("ready", provider, model_id)
            print(f"Transcription model loaded: {provider} / {model_id}")

    async def _cleanup_audio_and_transcriber(self) -> None:
        """Clean up audio capture and transcriber (called when prompting stops)."""
        if self.audio:
            self.audio.stop()
            self.audio = None
            print("Audio capture stopped")

        if self.transcriber:
            self.transcriber = None
            print("Transcriber unloaded")

    async def start(self) -> None:
        """Start the autocue application."""
        print("Starting Autocue...")

        print("Starting web server...")
        self.server = WebServer(
            host=self.host,
            port=self.port,
            initial_settings=self.display_settings
        )
        await self.server.start()

        # Don't start audio or load transcriber yet - wait for user to click Start
        self.running = True

        print("\n✓ Autocue ready!")
        print(f"  Open http://{self.host}:{self.port} in your browser")
        print("  Press Ctrl+C to stop\n")

        # Main processing loop - run as background task to keep event loop responsive
        print(f"[DEBUG] Creating process loop task at {time.time()}")
        process_task = asyncio.create_task(self._process_loop())

        # Wait for the process task to complete (only happens on shutdown)
        try:
            await process_task
        except asyncio.CancelledError:
            print("[DEBUG] Process task cancelled")

    async def _process_loop(self) -> None:
        """Main loop that processes audio and updates position."""
        assert self.server is not None, "Server must be initialized"
        current_script: str = ""
        current_transcription_config: TranscriptionConfig | None = None

        loop_start = time.time()
        iteration = 0

        while self.running:
            iteration += 1
            if iteration == 1:
                print(
                    f"[DEBUG] First loop iteration starting at {time.time()}, {time.time() - loop_start:.3f}s after loop entry")

            # Check for start prompting request
            if self.server.start_prompting_requested:
                self.server.start_prompting_requested = False
                # Check if model configuration has changed
                config = load_config()
                new_config = config.get("transcription", DEFAULT_CONFIG["transcription"])
                if (current_transcription_config is None or
                    new_config.get("provider") != current_transcription_config.get("provider") or
                    new_config.get("model_id") != current_transcription_config.get("model_id")):
                    # Model changed - reload transcriber
                    if self.transcriber:
                        self.transcriber = None
                        print("Transcription model changed, reloading...")
                    self.transcription_config = new_config
                    current_transcription_config = new_config.copy()

                # Also update audio device if it changed
                new_audio_device = config.get("audio_device")
                if new_audio_device != self.audio_device:
                    if self.audio:
                        self.audio.stop()
                        self.audio = None
                    self.audio_device = new_audio_device
                    print(f"Audio device changed to: {self.audio_device}")

                await self._initialize_audio_and_transcriber()

                # Reset tracker and transcriber to start from the beginning
                if self.tracker:
                    self.tracker.reset()
                    print("Tracker reset to beginning")

                if self.transcriber:
                    self.transcriber.reset()
                    print("Transcriber reset")

                print("Prompting started")

            # Check for stop prompting request
            if self.server.stop_prompting_requested:
                self.server.stop_prompting_requested = False
                await self._cleanup_audio_and_transcriber()
                # Stop transcript if running
                if self.save_transcript:
                    await self.stop_transcript()
                print("Prompting stopped")

            # Check if script has changed
            if self.server.script_text and self.server.script_text != current_script:
                current_script = self.server.script_text
                self.tracker = ScriptTracker(
                    current_script,
                    window_size=self.tracking_settings.get("window_size", 8),
                    match_threshold=self.tracking_settings.get(
                        "match_threshold", 65.0),
                    jump_threshold=self.tracking_settings.get(
                        "backtrack_threshold", 3),
                    max_jump_distance=self.tracking_settings.get(
                        "max_jump_distance", 50)
                )
                print(f"Script loaded: {len(self.tracker.words)} words")
                print(
                    f"Prompter started using transcription model: "
                    f"{self.transcription_config['model_id']} "
                    f"(provider: {self.transcription_config['provider']})"
                )
                # Clear debug logs for new session
                debug_log.clear_logs()
                # Reset last sent position for new script
                self._last_sent_word_index = None
                self._last_sent_line_index = None
                self._last_sent_word_offset = None
                # Start transcript if preference was set (via UI checkbox or CLI flag)
                if self.server.start_transcript_on_script or self.save_transcript:
                    self.server.start_transcript_on_script = False  # Reset flag
                    if not self.transcript_file:  # Don't restart if already recording
                        await self.start_transcript()

            # Check for reset request
            if self.server.reset_requested:
                self.server.reset_requested = False
                if self.tracker:
                    self.tracker.reset()
                    print("Position reset to beginning")
                    # Reset last sent position to force update
                    self._last_sent_word_index = None
                    self._last_sent_line_index = None
                    self._last_sent_word_offset = None

            # Check for jump request
            if self.server.jump_requested is not None:
                raw_token_index: int = self.server.jump_requested
                self.server.jump_requested = None
                if self.tracker and self.server.parsed_script:
                    # Convert raw token index to speakable index
                    # When a raw token maps to multiple speakable words (e.g., "2^3" → [2, ^, 3]),
                    # jump to the first speakable word from that raw token
                    speakable_indices = self.server.parsed_script.raw_to_speakable.get(
                        raw_token_index, [])
                    if speakable_indices:
                        speakable_index = speakable_indices[0]
                        self.tracker.jump_to(speakable_index)
                        print(
                            f"Jumped to raw token {raw_token_index} (speakable word {speakable_index})")
                    else:
                        # No speakable words for this raw token (shouldn't happen)
                        print(
                            f"Warning: No speakable words for raw token {raw_token_index}")
                    # Reset last sent position to force update
                    self._last_sent_word_index = None
                    self._last_sent_line_index = None
                    self._last_sent_word_offset = None

            # Check for transcript toggle request
            if self.server.transcript_toggle_requested is not None:
                enable: bool = self.server.transcript_toggle_requested
                self.server.transcript_toggle_requested = None
                if enable:
                    await self.start_transcript()
                else:
                    await self.stop_transcript()

            # Process audio - only if audio and transcriber are initialized
            if self.audio and self.transcriber:
                loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
                audio_chunk: bytes | None = await loop.run_in_executor(
                    None, self.audio.get_chunk, 0.05
                )
                if audio_chunk and self.tracker:
                    # Run blocking Vosk transcription in thread pool
                    result = await loop.run_in_executor(
                        None, self.transcriber.process_audio, audio_chunk
                    )

                    if result and result.text:
                        # Save transcript if enabled
                        self.write_transcript(result.text, result.is_partial)

                        position = self.tracker.update(
                            result.text,
                            is_partial=result.is_partial
                        )

                        # Get display info
                        _lines, _current_line_idx, word_offset = self.tracker.get_display_lines(
                            past_lines=self.server.settings.get("pastLines", 1),
                            future_lines=self.server.settings.get("futureLines", 8)
                        )

                        # Only send update if position has actually changed
                        position_changed: bool = (
                            position.word_index != self._last_sent_word_index or
                            position.line_index != self._last_sent_line_index or
                            word_offset != self._last_sent_word_offset
                        )

                        # Send update only when position changes
                        if position_changed:
                            # Send update to clients
                            await self.server.send_position(
                                word_index=position.word_index,
                                line_index=position.line_index,
                                word_offset=word_offset,
                                confidence=position.confidence,
                                is_backtrack=False,  # TODO: Fix this
                                transcript=result.text if result.is_partial else ""
                            )

                            # Update last sent position
                            self._last_sent_word_index = position.word_index
                            self._last_sent_line_index = position.line_index
                            self._last_sent_word_offset = word_offset

            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        """Stop the autocue application."""
        print("\nStopping Autocue...")
        self.running = False

        if self.audio:
            self.audio.stop()

        if self.server:
            await self.server.stop()

        print("Autocue stopped.")


def main() -> None:
    """Main entry point."""
    # Configure logging - minimal console output
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    # Disable verbose tracker logging
    logging.getLogger("autocue.tracker").setLevel(logging.WARNING)

    # Load config first to use as defaults
    config: Config = load_config()

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Autocue - Low-latency teleprompter with speech tracking"
    )

    # Transcription options
    transcription_config = config.get(
        "transcription", DEFAULT_CONFIG["transcription"])

    parser.add_argument(
        "--provider",
        default=transcription_config.get("provider", "vosk"),
        choices=["vosk", "sherpa"],
        help="Transcription provider (default: from config or 'vosk')"
    )

    parser.add_argument(
        "--model-id",
        default=transcription_config.get("model_id"),
        help="Model identifier (e.g., 'vosk-en-us-small', 'sherpa-zipformer-en-2023-06-26')"
    )

    parser.add_argument(
        "--model-path",
        default=transcription_config.get("model_path"),
        help="Path to custom model directory (optional)"
    )

    # Legacy options (deprecated)
    parser.add_argument(
        "--model", "-m",
        default=None,
        choices=["small", "medium", "large"],
        help="[DEPRECATED] Vosk model size (use --model-id instead)"
    )

    parser.add_argument(
        "--host",
        default=config.get("host", "127.0.0.1"),
        help="Web server host (default: from config or 127.0.0.1)"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=config.get("port", 8000),
        help="Web server port (default: from config or 8000)"
    )

    parser.add_argument(
        "--device", "-d",
        type=int,
        default=config.get("audio_device"),
        help="Audio input device index"
    )

    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit"
    )

    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all available transcription models and exit"
    )

    parser.add_argument(
        "--download-model",
        action="store_true",
        help="Download the specified model and exit"
    )

    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=config.get("chunk_ms", 100),
        help="Audio chunk size in milliseconds (default: from config or 100)"
    )

    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Save current CLI options to config file and exit"
    )

    parser.add_argument(
        "--save-transcript",
        action="store_true",
        help="Save a transcript of all recognized speech to ./transcripts/"
    )

    parser.add_argument(
        "--debug-log",
        action="store_true",
        help="Enable debug logging to ./logs/"
    )

    args: argparse.Namespace = parser.parse_args()

    # Handle special commands
    if args.list_devices:
        list_devices()
        return

    if args.list_models:
        models = get_all_available_models()
        print("\nAvailable transcription models:")
        print("-" * 80)
        current_provider = None
        for model in sorted(models, key=lambda m: (m.provider, m.name)):
            if model.provider != current_provider:
                current_provider = model.provider
                print(f"\n{model.provider.upper()} Models:")
            print(f"  {model.id}")
            print(f"    Name: {model.name}")
            print(f"    Size: {model.size_mb}MB")
            if model.description:
                print(f"    Description: {model.description}")
            print()
        return

    if args.download_model:
        # Determine model_id from args
        if args.model_id:
            model_id = args.model_id
        elif args.model:
            # Legacy model name - convert to model_id
            model_id = f"vosk-en-us-{args.model}"
        else:
            model_id = transcription_config.get("model_id", "vosk-en-us-small")

        print(f"Downloading model: {model_id}")
        download_model(model_id)
        return

    if args.save_config:
        # Save current CLI options to config
        # Build transcription config from CLI args
        if args.model_id:
            config["transcription"]["model_id"] = args.model_id
        elif args.model:
            # Legacy format - convert
            config["transcription"]["model_id"] = f"vosk-en-us-{args.model}"

        if args.provider:
            config["transcription"]["provider"] = args.provider

        if args.model_path:
            config["transcription"]["model_path"] = args.model_path

        config["host"] = args.host
        config["port"] = args.port
        config["audio_device"] = args.device
        config["chunk_ms"] = args.chunk_ms

        # Clear legacy fields
        config["model"] = None
        config["model_path"] = None

        if save_config(config):
            print(f"Configuration saved to {get_config_path()}")
        return

    # Enable debug logging if requested
    if args.debug_log:
        debug_log.enable()
        print("Debug logging enabled (logs will be saved to ./logs/)")

    # Build transcription config from CLI args and config file
    final_transcription_config: TranscriptionConfig = {
        "provider": args.provider,
        "model_id": args.model_id or transcription_config.get("model_id", "vosk-en-us-small"),
        "model_path": args.model_path,
    }

    # Handle legacy --model argument
    if args.model and not args.model_id:
        final_transcription_config["model_id"] = f"vosk-en-us-{args.model}"

    # Create and run the app
    app: AutocueApp = AutocueApp(
        transcription_config=final_transcription_config,
        host=args.host,
        port=args.port,
        audio_device=args.device,
        chunk_ms=args.chunk_ms,
        display_settings=get_display_settings(config),
        tracking_settings=get_tracking_settings(config),
        save_transcript=args.save_transcript
    )

    # Handle shutdown gracefully
    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    shutdown_event: asyncio.Event = asyncio.Event()

    def shutdown(sig: int, frame: object) -> None:
        """Handle shutdown signals (SIGINT, SIGTERM) gracefully."""
        print("\nReceived shutdown signal...")
        # Set the running flag to false to stop the main loop
        app.running = False
        # Schedule setting the shutdown event on the loop
        loop.call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(app.start())
    except KeyboardInterrupt:
        app.running = False
    finally:
        # Ensure clean shutdown
        with contextlib.suppress(Exception):
            loop.run_until_complete(app.stop())
        # Cancel any remaining tasks
        pending: set[asyncio.Task[object]] = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Allow cancelled tasks to complete
        if pending:
            loop.run_until_complete(asyncio.gather(
                *pending, return_exceptions=True))
        loop.close()


if __name__ == "__main__":
    main()
