# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Web server for the autocue interface.
Serves the HTML UI and handles WebSocket connections for real-time updates.
"""

import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import markdown
import sounddevice as sd
from aiohttp import web

from . import debug_log
from .config import DEFAULT_CONFIG, DisplaySettings, load_config, save_config, update_config_display
from .providers import download_model_with_progress, get_all_available_models, is_model_downloaded
from .script_parser import ParsedScript, RawToken, parse_script

logger = logging.getLogger(__name__)


class WordIndexingHTMLParser(HTMLParser):
    """HTML parser that wraps text words with span elements containing raw token indices.

    Uses the ParsedScript to map each raw token to its index, ensuring the UI
    highlights match what the tracker returns.
    """

    def __init__(self, parsed_script: ParsedScript) -> None:
        super().__init__()
        self.parsed_script: ParsedScript = parsed_script
        # Build a map from raw token text (lowercased) at each position to its index
        # This handles the case where the same word appears multiple times
        self.raw_token_iter: Iterator[RawToken] = iter(
            parsed_script.raw_tokens)
        self.current_raw_token: RawToken | None = None
        self._advance_token()
        self.output: list[str] = []
        self.tag_stack: list[str] = []

    def _advance_token(self) -> None:
        """Move to the next raw token."""
        try:
            self.current_raw_token = next(self.raw_token_iter)
        except StopIteration:
            self.current_raw_token = None

    def _token_matches(self, text: str) -> bool:
        """Check if the current raw token matches the given text."""
        if self.current_raw_token is None:
            return False
        # Compare normalized versions
        return self.current_raw_token.text.lower() == text.lower()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening HTML tags."""
        attrs_str: str = ''.join(f' {k}="{v}"' for k, v in attrs)
        self.output.append(f'<{tag}{attrs_str}>')
        self.tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        """Handle closing HTML tags."""
        self.output.append(f'</{tag}>')
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle self-closing HTML tags."""
        attrs_str: str = ''.join(f' {k}="{v}"' for k, v in attrs)
        self.output.append(f'<{tag}{attrs_str}/>')

    def handle_data(self, data: str) -> None:
        """Process text data, wrapping words with indexed spans."""
        if not data.strip():
            # Preserve whitespace-only text
            self.output.append(data)
            return

        # Split text into words and whitespace, preserving order
        parts = re.split(r'(\s+)', data)
        result = []

        for part in parts:
            if not part:
                continue
            if part.isspace():
                # Preserve whitespace as-is
                result.append(part)
            else:
                # Escape HTML entities
                escaped = part.replace('&', '&amp;').replace(
                    '<', '&lt;').replace('>', '&gt;')

                # Check if this matches the current raw token
                if self._token_matches(part) and self.current_raw_token is not None:
                    # Wrap with span using the raw token index
                    idx = self.current_raw_token.index
                    result.append(
                        f'<span class="word" data-word-index="{idx}">{escaped}</span>')
                    self._advance_token()
                else:
                    # No matching token - output as-is (shouldn't happen normally)
                    result.append(escaped)

        self.output.append(''.join(result))

    def handle_entityref(self, name: str) -> None:
        """Handle HTML entity references like &amp;."""
        self.output.append(f'&{name};')

    def handle_charref(self, name: str) -> None:
        """Handle HTML character references like &#39;."""
        self.output.append(f'&#{name};')

    def get_output(self) -> str:
        """Return the processed HTML output."""
        return ''.join(self.output)


def render_script_with_word_indices(script_text: str) -> tuple[str, int, ParsedScript]:
    """Render script to HTML with each word wrapped in an indexed span.

    Uses the three-version script parser to ensure:
    - Raw tokens get unique indices for UI highlighting
    - Speakable words (with punctuation expansion) are used for matching
    - Indices map correctly between tracker and UI

    Args:
        script_text: The raw script text (may contain Markdown)

    Returns:
        Tuple of (html_with_word_spans, total_raw_tokens, parsed_script)
    """
    # Step 1: Render markdown to HTML
    raw_html = markdown.markdown(
        script_text,
        extensions=['nl2br', 'sane_lists']
    )

    # Step 2: Parse script using three-version parser with rendered HTML
    # This extracts tokens from what actually appears in the HTML
    parsed_script = parse_script(script_text, raw_html)

    # Step 3: Parse HTML and wrap words with indexed spans
    parser = WordIndexingHTMLParser(parsed_script)
    parser.feed(raw_html)
    indexed_html = parser.get_output()

    return indexed_html, parsed_script.total_raw_tokens, parsed_script


class WebServer:
    """
    Serves the autocue web interface and manages WebSocket connections.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        initial_settings: DisplaySettings | None = None,
        samples_dir: str | None = None
    ) -> None:
        self.host: str = host
        self.port: int = port
        self.app: web.Application = web.Application()
        self.websockets: set[web.WebSocketResponse] = set()
        self.runner: web.AppRunner | None = None

        # Sample scripts directory
        if samples_dir:
            self.samples_dir: Path = Path(samples_dir)
        else:
            # Default to samples/ in the project root
            self.samples_dir = Path(__file__).parent.parent.parent / "samples"

        # Current state
        self.script_text: str = ""
        self.script_html: str = ""
        self.total_words: int = 0
        self.parsed_script: ParsedScript | None = None
        self.reset_requested: bool = False
        self.jump_requested: int | None = None
        # True=start, False=stop
        self.transcript_toggle_requested: bool | None = None
        # Start transcript when script loads
        self.start_transcript_on_script: bool = False
        # Prompting state control
        self.start_prompting_requested: bool = False
        self.stop_prompting_requested: bool = False
        self.is_prompting: bool = False

        # Merge initial settings with defaults
        self.settings = DEFAULT_CONFIG["display"].copy()
        if initial_settings:
            self.settings.update(initial_settings)

        self._setup_routes()

    def _get_sample_scripts(self) -> list[dict[str, str]]:
        """Get list of available sample scripts."""
        samples: list[dict[str, str]] = []
        if self.samples_dir.exists():
            for f in sorted(self.samples_dir.glob("*.md")):
                samples.append({
                    "name": f.stem.replace("_", " ").title(),
                    "filename": f.name
                })
        return samples

    def _load_sample_script(self, filename: str) -> str | None:
        """Load a sample script by filename."""
        if not filename:
            return None
        # Sanitize filename to prevent path traversal
        safe_name: str = Path(filename).name
        script_path: Path = self.samples_dir / safe_name
        if script_path.exists() and script_path.suffix == ".md":
            return script_path.read_text(encoding="utf-8")
        return None

    def _setup_routes(self) -> None:
        """Set up HTTP routes."""
        self.app.router.add_get('/', self._handle_index)
        self.app.router.add_get('/ws', self._handle_websocket)
        self.app.router.add_post('/script', self._handle_script_upload)
        self.app.router.add_post('/settings', self._handle_settings)
        self.app.router.add_get('/settings', self._handle_get_settings)
        self.app.router.add_post('/save-config', self._handle_save_config)
        self.app.router.add_get(
            '/audio-devices', self._handle_get_audio_devices)

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the main HTML page."""
        html = self._get_html()
        return web.Response(text=html, content_type='text/html')

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time updates."""
        start_time = time.time()
        print(f"[WS] Connection attempt received at {start_time}")

        ws = web.WebSocketResponse()
        prepare_start = time.time()
        await ws.prepare(request)
        print(f"[WS] prepare() took {time.time() - prepare_start:.3f}s")

        self.websockets.add(ws)
        print(
            f"[WS] WebSocket connected in {time.time() - start_time:.3f}s. Total: {len(self.websockets)}")

        try:
            # Send current state
            config = load_config()
            await ws.send_json({
                "type": "init",
                "script": self.script_text,
                "scriptHtml": self.script_html,
                "totalWords": self.total_words,
                "settings": self.settings,
                "samples": self._get_sample_scripts(),
                "audioDevice": config.get("audio_device"),
                "transcriptionConfig": config.get("transcription", DEFAULT_CONFIG["transcription"])
            })

            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_ws_message(ws, data)
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"WebSocket error: {ws.exception()}")
        finally:
            self.websockets.discard(ws)
            print(f"WebSocket disconnected. Total: {len(self.websockets)}")

        return ws

    async def _handle_ws_message(self, ws: web.WebSocketResponse, data: dict[str, object]) -> None:
        """Handle incoming WebSocket messages using dispatch pattern."""
        msg_type: object | None = data.get("type")
        if not msg_type:
            return

        # Message type to handler dispatch
        handlers: dict[str, object] = {
            "script": self._on_script_message,
            "settings": self._on_settings_message,
            "reset": self._on_reset_message,
            "jump_to": self._on_jump_to_message,
            "save_config": self._on_save_config_message,
            "frontend_highlight": self._on_frontend_highlight_message,
            "load_sample": self._on_load_sample_message,
            "toggle_transcript": self._on_toggle_transcript_message,
            "set_audio_device": self._on_set_audio_device_message,
            "get_transcription_models": self._on_get_transcription_models,
            "set_transcription_config": self._on_set_transcription_config,
            "check_model_downloaded": self._on_check_model_downloaded,
            "download_model": self._on_download_model,
            "start_prompting": self._on_start_prompting_message,
            "stop_prompting": self._on_stop_prompting_message,
        }

        handler: object | None = handlers.get(
            msg_type)  # type: ignore[arg-type]
        if handler:
            await handler(ws, data)  # type: ignore[operator]
        else:
            logger.warning("Unhandled WebSocket message: %s", msg_type)

    async def _on_script_message(self, _ws: web.WebSocketResponse, data: dict[str, object]) -> None:
        """Handle script update message."""
        self.script_text = str(data.get("text", ""))
        self.start_transcript_on_script = bool(
            data.get("saveTranscript", False))
        await self._render_and_broadcast_script()

    async def _on_settings_message(
        self,
        _ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle settings update message."""
        settings_update = data.get("settings", {})
        self.settings.update(settings_update)  # type: ignore
        await self.broadcast({
            "type": "settings_updated",
            "settings": self.settings
        })

    async def _on_reset_message(self, _ws: web.WebSocketResponse, _data: dict[str, object]) -> None:
        """Handle reset message."""
        await self.broadcast({"type": "reset"})
        self.reset_requested = True

    async def _on_jump_to_message(
        self,
        _ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle jump to position message."""
        word_index_raw: object = data.get("wordIndex", 0)
        word_index: int = int(word_index_raw) if isinstance(
            word_index_raw, (int, float, str)) else 0
        await self.broadcast({
            "type": "jump_to",
            "wordIndex": word_index
        })
        self.jump_requested = word_index

    async def _on_save_config_message(
        self,
        ws: web.WebSocketResponse,
        _data: dict[str, object]
    ) -> None:
        """Handle save config message."""
        try:
            config = load_config()
            config = update_config_display(config, self.settings)
            success = save_config(config)
            await ws.send_json({
                "type": "config_saved",
                "success": success
            })
        except Exception as e:
            await ws.send_json({
                "type": "config_saved",
                "success": False,
                "error": str(e)
            })

    async def _on_frontend_highlight_message(
        self,
        _ws: web.WebSocketResponse,
        data: dict[str, Any]
    ) -> None:
        """Handle frontend highlight debug message."""
        word_index: int = int(data.get(
            "wordIndex", -1)) if isinstance(data.get("wordIndex", -1), (int, float)) else -1
        word: str = str(data.get("word", ""))
        source_line: int = int(data.get(
            "sourceLine", -1)) if isinstance(data.get("sourceLine", -1), (int, float)) else -1
        source_offset: int = int(data.get(
            "sourceOffset", -1)) if isinstance(data.get("sourceOffset", -1), (int, float)) else -1
        server_word_index: int = int(data.get("serverWordIndex", -1)) if isinstance(
            data.get("serverWordIndex", -1), (int, float)) else -1
        debug_log.log_frontend_word(
            word_index, word, source_line, source_offset)
        debug_log.log_frontend_server_data(
            server_word_index, source_line, source_offset)

    async def _on_load_sample_message(
        self,
        _ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle load sample script message."""
        filename: str = str(data.get("filename", ""))
        content: str | None = self._load_sample_script(filename)
        if content is not None:
            self.script_text = content
            await self._render_and_broadcast_script()

    async def _on_toggle_transcript_message(
        self,
        _ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle toggle transcript message."""
        self.transcript_toggle_requested = bool(data.get("enable", False))

    async def _on_set_audio_device_message(
        self,
        ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle set audio device message."""
        device_index: object | None = data.get("deviceIndex")
        try:
            config = load_config()
            config["audio_device"] = device_index  # type: ignore
            if save_config(config):
                await ws.send_json({
                    "type": "audio_device_updated",
                    "success": True,
                    "deviceIndex": device_index
                })
                await self.broadcast({
                    "type": "audio_device_updated",
                    "success": True,
                    "deviceIndex": device_index
                })
            else:
                await ws.send_json({
                    "type": "audio_device_updated",
                    "success": False,
                    "error": "Failed to save config"
                })
        except Exception as e:
            await ws.send_json({
                "type": "audio_device_updated",
                "success": False,
                "error": str(e)
            })

    async def _on_get_transcription_models(
        self,
        ws: web.WebSocketResponse,
        _data: dict[str, object]
    ) -> None:
        """Handle get transcription models message."""
        try:
            models = get_all_available_models()
            await ws.send_json({
                "type": "transcription_models",
                "models": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "provider": m.provider,
                        "sizeMb": m.size_mb,
                        "description": m.description,
                    }
                    for m in models
                ]
            })
        except Exception as e:
            logger.error("Error getting transcription models: %s", e)
            await ws.send_json({
                "type": "transcription_models",
                "models": [],
                "error": str(e)
            })

    async def _on_set_transcription_config(
        self,
        ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle set transcription config message."""
        provider: str = str(data.get("provider", "vosk"))
        model_id: str = str(data.get("modelId", "vosk-en-us-small"))

        try:
            config = load_config()
            config["transcription"]["provider"] = provider
            config["transcription"]["model_id"] = model_id
            config["transcription"]["model_path"] = None

            if save_config(config):
                await ws.send_json({
                    "type": "transcription_config_updated",
                    "success": True,
                    "message": "Settings saved. Stop and start prompting to apply changes."
                })
                # Broadcast to all clients
                await self.broadcast({
                    "type": "transcription_config_updated",
                    "success": True,
                    "message": "Settings saved. Stop and start prompting to apply changes."
                })
            else:
                await ws.send_json({
                    "type": "transcription_config_updated",
                    "success": False,
                    "error": "Failed to save config"
                })
        except Exception as e:
            logger.error("Error setting transcription config: %s", e)
            await ws.send_json({
                "type": "transcription_config_updated",
                "success": False,
                "error": str(e)
            })

    async def _on_check_model_downloaded(
        self,
        ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle check model downloaded message."""
        provider: str = str(data.get("provider", "vosk"))
        model_id: str = str(data.get("modelId", ""))

        try:
            downloaded = is_model_downloaded(provider, model_id)
            await ws.send_json({
                "type": "model_download_status",
                "provider": provider,
                "modelId": model_id,
                "downloaded": downloaded
            })
        except Exception as e:
            logger.error("Error checking model download status: %s", e)
            await ws.send_json({
                "type": "model_download_status",
                "provider": provider,
                "modelId": model_id,
                "downloaded": False,
                "error": str(e)
            })

    async def _on_download_model(
        self,
        ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle download model message with progress updates."""
        provider: str = str(data.get("provider", "vosk"))
        model_id: str = str(data.get("modelId", ""))

        try:
            # Send initial starting message
            await ws.send_json({
                "type": "model_download_progress",
                "provider": provider,
                "modelId": model_id,
                "stage": "starting",
                "percent": 0
            })

            # Create progress callback that sends updates via WebSocket
            async def progress_callback(stage: str, percent: int) -> None:
                await ws.send_json({
                    "type": "model_download_progress",
                    "provider": provider,
                    "modelId": model_id,
                    "stage": stage,
                    "percent": percent
                })

            # Run download in executor to avoid blocking
            loop = asyncio.get_event_loop()

            def sync_progress_callback(stage: str, percent: int) -> None:
                # Schedule the async callback in the event loop
                asyncio.run_coroutine_threadsafe(
                    progress_callback(stage, percent), loop
                )

            model_path = await loop.run_in_executor(
                None,
                lambda: download_model_with_progress(
                    provider, model_id, sync_progress_callback
                )
            )

            # Send completion message
            await ws.send_json({
                "type": "model_download_complete",
                "provider": provider,
                "modelId": model_id,
                "success": True,
                "path": model_path,
                "message": "Model downloaded successfully. Start prompting to use it."
            })
            # Broadcast to all clients
            await self.broadcast({
                "type": "model_download_complete",
                "provider": provider,
                "modelId": model_id,
                "success": True,
                "message": "Model downloaded successfully. Start prompting to use it."
            })
        except Exception as e:
            logger.error("Error downloading model: %s", e)
            await ws.send_json({
                "type": "model_download_complete",
                "provider": provider,
                "modelId": model_id,
                "success": False,
                "error": str(e)
            })
            # Broadcast to all clients
            await self.broadcast({
                "type": "model_download_complete",
                "provider": provider,
                "modelId": model_id,
                "success": False,
                "error": str(e)
            })

    async def _on_start_prompting_message(
        self,
        ws: web.WebSocketResponse,
        data: dict[str, object]
    ) -> None:
        """Handle start prompting message."""
        self.start_prompting_requested = True
        self.is_prompting = True
        # Include transcript preference
        self.start_transcript_on_script = bool(data.get("saveTranscript", False))
        logger.info("Start prompting requested")

    async def _on_stop_prompting_message(
        self,
        _ws: web.WebSocketResponse,
        _data: dict[str, object]
    ) -> None:
        """Handle stop prompting message."""
        self.stop_prompting_requested = True
        self.is_prompting = False
        logger.info("Stop prompting requested")

    async def _render_and_broadcast_script(self) -> None:
        """Render script to HTML and broadcast to all clients."""
        self.script_html, self.total_words, self.parsed_script = render_script_with_word_indices(
            self.script_text
        )
        await self.broadcast({
            "type": "script_updated",
            "script": self.script_text,
            "scriptHtml": self.script_html,
            "totalWords": self.total_words
        })

    async def _handle_script_upload(self, request: web.Request) -> web.Response:
        """Handle script upload via POST."""
        data: dict[str, object] = await request.json()
        self.script_text = str(data.get("text", ""))
        # Render with word indices embedded in the HTML
        self.script_html, self.total_words, self.parsed_script = render_script_with_word_indices(
            self.script_text
        )
        await self.broadcast({
            "type": "script_updated",
            "script": self.script_text,
            "scriptHtml": self.script_html,
            "totalWords": self.total_words
        })
        return web.json_response({"status": "ok"})

    async def _handle_settings(self, request: web.Request) -> web.Response:
        """Handle settings update via POST."""
        data = await request.json()
        self.settings.update(data)
        await self.broadcast({
            "type": "settings_updated",
            "settings": self.settings
        })
        return web.json_response({"status": "ok", "settings": self.settings})

    async def _handle_get_settings(self, request: web.Request) -> web.Response:
        """Get current settings."""
        return web.json_response(self.settings)

    async def _handle_save_config(self, request: web.Request) -> web.Response:
        """Save current settings to config file."""
        try:
            config = load_config()
            config = update_config_display(config, self.settings)
            if save_config(config):
                return web.json_response({"status": "ok", "message": "Settings saved"})
            else:
                return web.json_response(
                    {"status": "error", "message": "Failed to save config"},
                    status=500
                )
        except Exception as e:
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )

    async def _handle_get_audio_devices(self, request: web.Request) -> web.Response:
        """Get list of available audio input devices."""
        try:
            devices: object = sd.query_devices()
            device_list: list[dict[str, object]] = []
            for i, device in enumerate(devices):  # type: ignore[arg-type]
                dev: dict[str, object] = dict(device)  # type: ignore[arg-type]
                if int(dev['max_input_channels']) > 0:  # type: ignore[arg-type]
                    device_list.append({
                        "index": i,
                        "name": dev['name'],
                        "channels": dev['max_input_channels']
                    })
            return web.json_response({
                "status": "ok",
                "devices": device_list
            })
        except Exception as e:
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=500
            )

    async def broadcast(self, message: dict[str, object]) -> None:
        """Send a message to all connected WebSocket clients."""
        if not self.websockets:
            return

        dead: set[web.WebSocketResponse] = set()
        for ws in self.websockets:
            try:
                await ws.send_json(message)
            except (ConnectionError, ConnectionResetError, RuntimeError) as e:
                print(f"Error sending to WebSocket: {e}")
                dead.add(ws)

        self.websockets -= dead

    async def send_transcript_status(self, recording: bool, file: str | None = None) -> None:
        """Send transcript recording status to all clients."""
        await self.broadcast({
            "type": "transcript_status",
            "recording": recording,
            "file": str(file) if file else None
        })

    async def send_model_loading_status(self, status: str, provider: str, model_id: str) -> None:
        """Send model loading status to all clients.

        Args:
            status: Either 'loading' or 'ready'
            provider: The transcription provider (e.g., 'vosk', 'sherpa')
            model_id: The model identifier
        """
        await self.broadcast({
            "type": "model_loading_status",
            "status": status,
            "provider": provider,
            "modelId": model_id
        })

    async def send_position(
        self,
        word_index: int,
        line_index: int,
        word_offset: int,
        confidence: float,
        is_backtrack: bool,
        transcript: str = ""
    ) -> None:
        """Send position update to all clients."""
        if is_backtrack:
            logger.warning(
                "[SERVER BROADCAST] Sending isBacktrack=True to %d client(s), "
                "wordIndex=%d, lineIndex=%d",
                len(self.websockets), word_index, line_index
            )
        await self.broadcast({
            "type": "position",
            "wordIndex": word_index,
            "lineIndex": line_index,
            "wordOffset": word_offset,
            "confidence": confidence,
            "isBacktrack": is_backtrack,
            "transcript": transcript
        })

    async def start(self) -> None:
        """Start the web server."""
        start_time = time.time()
        print(f"[SERVER] Starting web server setup at {start_time}")

        self.runner = web.AppRunner(self.app)
        setup_start = time.time()
        await self.runner.setup()
        print(f"[SERVER] runner.setup() took {time.time() - setup_start:.3f}s")

        site_create_start = time.time()
        site: web.TCPSite = web.TCPSite(self.runner, self.host, self.port)
        print(
            f"[SERVER] TCPSite created in {time.time() - site_create_start:.3f}s")

        site_start_time = time.time()
        await site.start()
        print(
            f"[SERVER] site.start() took {time.time() - site_start_time:.3f}s")
        print(
            f"[SERVER] Total server start time: {time.time() - start_time:.3f}s")
        print(f"Web server running at http://{self.host}:{self.port}")

        # Give event loop a moment to start accepting connections
        print("[SERVER] Yielding to event loop...")
        await asyncio.sleep(0.1)
        print(f"[SERVER] Server should be fully ready now at {time.time()}")

    async def stop(self) -> None:
        """Stop the web server."""
        # Close all WebSocket connections
        for ws in list(self.websockets):
            with contextlib.suppress(Exception):
                await ws.close()
        self.websockets.clear()

        if self.runner:
            await self.runner.cleanup()

    def _get_html(self) -> str:
        """Load and return the HTML for the autocue interface from static/index.html."""
        static_dir: Path = Path(__file__).parent / "static"
        html_path: Path = static_dir / "index.html"
        return html_path.read_text(encoding="utf-8")
