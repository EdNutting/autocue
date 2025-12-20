"""
Main autocue application.
Orchestrates audio capture, transcription, script tracking, and the web UI.
"""

import asyncio
import argparse
import logging
import signal
import sys
import threading
from typing import Optional

logger = logging.getLogger(__name__)

from .audio import AudioCapture, list_devices
from .transcribe import Transcriber, download_model
from .tracker import ScriptTracker
from .server import WebServer
from .config import (
    load_config, save_config, get_config_path,
    get_display_settings, get_tracking_settings
)
from . import debug_log


class AutocueApp:
    """
    Main autocue application that coordinates all components.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        model_name: str = "small",
        host: str = "127.0.0.1",
        port: int = 8765,
        audio_device: Optional[int] = None,
        chunk_ms: int = 100,
        display_settings: Optional[dict] = None,
        tracking_settings: Optional[dict] = None
    ):
        self.model_path = model_path
        self.model_name = model_name
        self.host = host
        self.port = port
        self.audio_device = audio_device
        self.chunk_ms = chunk_ms
        self.display_settings = display_settings or {}
        self.tracking_settings = tracking_settings or {}

        self.audio: Optional[AudioCapture] = None
        self.transcriber: Optional[Transcriber] = None
        self.tracker: Optional[ScriptTracker] = None
        self.server: Optional[WebServer] = None

        self.running = False
        self.audio_thread: Optional[threading.Thread] = None
        
    async def start(self):
        """Start the autocue application."""
        print("Starting Autocue...")
        
        # Initialize components
        print("Initializing audio capture...")
        self.audio = AudioCapture(
            chunk_duration_ms=self.chunk_ms,
            device=self.audio_device
        )
        
        print("Loading speech recognition model...")
        self.transcriber = Transcriber(
            model_path=self.model_path,
            model_name=self.model_name
        )
        
        print("Starting web server...")
        self.server = WebServer(
            host=self.host,
            port=self.port,
            initial_settings=self.display_settings
        )
        await self.server.start()
        
        print(f"\n✓ Autocue ready!")
        print(f"  Open http://{self.host}:{self.port} in your browser")
        print(f"  Press Ctrl+C to stop\n")
        
        # Start audio processing
        self.running = True
        self.audio.start()
        
        # Main processing loop
        await self._process_loop()
        
    async def _process_loop(self):
        """Main loop that processes audio and updates position."""
        current_script = ""
        
        while self.running:
            # Check if script has changed
            if self.server.script_text and self.server.script_text != current_script:
                current_script = self.server.script_text
                self.tracker = ScriptTracker(
                    current_script,
                    window_size=self.tracking_settings.get("window_size", 8),
                    match_threshold=self.tracking_settings.get("match_threshold", 65.0),
                    backtrack_threshold=self.tracking_settings.get("backtrack_threshold", 3),
                    max_jump_distance=self.tracking_settings.get("max_jump_distance", 50)
                )
                print(f"Script loaded: {len(self.tracker.words)} words")
                # Clear debug logs for new session
                debug_log.clear_logs()
                
            # Check for reset request
            if self.server._reset_requested:
                self.server._reset_requested = False
                if self.tracker:
                    self.tracker.reset()
                    print("Position reset to beginning")

            # Check for jump request
            if self.server._jump_requested is not None:
                jump_to = self.server._jump_requested
                self.server._jump_requested = None
                if self.tracker:
                    self.tracker.jump_to(jump_to)
                    print(f"Jumped to word index {jump_to}")

            # Process audio
            audio_chunk = self.audio.get_chunk(timeout=0.05)
            if audio_chunk and self.tracker:
                result = self.transcriber.process_audio(audio_chunk)

                if result and result.text:
                    # Update position using optimistic matching (fast path)
                    position = self.tracker.update(
                        result.text,
                        is_partial=result.is_partial
                    )

                    # Check if validation is needed (every 5 words)
                    is_backtrack = False
                    if self.tracker.needs_validation:
                        logger.debug(
                            "[VALIDATION] Triggering validation at position %d",
                            position.word_index
                        )
                        validated_pos, is_backtrack = self.tracker.validate_position(result.text)
                        if is_backtrack or validated_pos != position.word_index:
                            # Position was corrected by validation
                            logger.info(
                                "[VALIDATION RESULT] is_backtrack=%s, validated_pos=%d, "
                                "original_pos=%d",
                                is_backtrack, validated_pos, position.word_index
                            )
                            position = self.tracker._current_position()
                            position.is_backtrack = is_backtrack
                        if is_backtrack:
                            logger.warning(
                                "[BACKTRACK] Sending backtrack signal to clients, "
                                "new position=%d",
                                position.word_index
                            )

                    # Get display info
                    lines, current_line_idx, word_offset = self.tracker.get_display_lines(
                        past_lines=self.server.settings.get("pastLines", 1),
                        future_lines=self.server.settings.get("futureLines", 8)
                    )

                    # Log what we're sending to the client
                    word_at_pos = self.tracker.words[position.word_index] if position.word_index < len(self.tracker.words) else "END"
                    debug_log.log_server_word(
                        position.word_index, word_at_pos,
                        f"SEND line={position.line_index} offset={word_offset}"
                    )

                    # Send update to clients
                    await self.server.send_position(
                        word_index=position.word_index,
                        line_index=position.line_index,
                        word_offset=word_offset,
                        confidence=position.confidence,
                        is_backtrack=is_backtrack,
                        transcript=result.text if result.is_partial else ""
                    )
                    
            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.01)
            
    async def stop(self):
        """Stop the autocue application."""
        print("\nStopping Autocue...")
        self.running = False
        
        if self.audio:
            self.audio.stop()
            
        if self.server:
            await self.server.stop()
            
        print("Autocue stopped.")


def main():
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
    config = load_config()

    parser = argparse.ArgumentParser(
        description="Autocue - Low-latency teleprompter with speech tracking"
    )

    parser.add_argument(
        "--model", "-m",
        default=config.get("model", "small"),
        choices=["small", "medium", "large"],
        help="Vosk model size (default: from config or 'small')"
    )

    parser.add_argument(
        "--model-path",
        default=config.get("model_path"),
        help="Path to Vosk model directory (overrides --model)"
    )

    parser.add_argument(
        "--host",
        default=config.get("host", "127.0.0.1"),
        help="Web server host (default: from config or 127.0.0.1)"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=config.get("port", 8765),
        help="Web server port (default: from config or 8765)"
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

    args = parser.parse_args()
    
    # Handle special commands
    if args.list_devices:
        list_devices()
        return

    if args.download_model:
        download_model(args.model)
        return

    if args.save_config:
        # Save current CLI options to config
        config["model"] = args.model
        config["model_path"] = args.model_path
        config["host"] = args.host
        config["port"] = args.port
        config["audio_device"] = args.device
        config["chunk_ms"] = args.chunk_ms
        if save_config(config):
            print(f"Configuration saved to {get_config_path()}")
        return

    # Create and run the app
    app = AutocueApp(
        model_path=args.model_path,
        model_name=args.model,
        host=args.host,
        port=args.port,
        audio_device=args.device,
        chunk_ms=args.chunk_ms,
        display_settings=get_display_settings(config),
        tracking_settings=get_tracking_settings(config)
    )
    
    # Handle shutdown gracefully
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    shutdown_event = asyncio.Event()

    def shutdown(sig, frame):
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
        try:
            loop.run_until_complete(app.stop())
        except Exception:
            pass
        # Cancel any remaining tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Allow cancelled tasks to complete
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


if __name__ == "__main__":
    main()
