"""
Web server for the autocue interface.
Serves the HTML UI and handles WebSocket connections for real-time updates.
"""

import asyncio
import json
import logging
import re
import markdown
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional, Set, List, Tuple, Dict
from aiohttp import web

from .config import load_config, save_config, update_config_display
from . import debug_log
from .script_parser import (
    ParsedScript, parse_script, RawToken,
    PUNCTUATION_EXPANSIONS, is_silent_punctuation
)
import sounddevice as sd

logger = logging.getLogger(__name__)


class WordIndexingHTMLParser(HTMLParser):
    """HTML parser that wraps text words with span elements containing raw token indices.

    Uses the ParsedScript to map each raw token to its index, ensuring the UI
    highlights match what the tracker returns.
    """

    def __init__(self, parsed_script: ParsedScript):
        super().__init__()
        self.parsed_script = parsed_script
        # Build a map from raw token text (lowercased) at each position to its index
        # This handles the case where the same word appears multiple times
        self.raw_token_iter = iter(parsed_script.raw_tokens)
        self.current_raw_token: Optional[RawToken] = None
        self._advance_token()
        self.output = []
        self.tag_stack = []

    def _advance_token(self):
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

    def handle_starttag(self, tag, attrs):
        """Handle opening HTML tags."""
        attrs_str = ''.join(f' {k}="{v}"' for k, v in attrs)
        self.output.append(f'<{tag}{attrs_str}>')
        self.tag_stack.append(tag)

    def handle_endtag(self, tag):
        """Handle closing HTML tags."""
        self.output.append(f'</{tag}>')
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()

    def handle_startendtag(self, tag, attrs):
        """Handle self-closing HTML tags."""
        attrs_str = ''.join(f' {k}="{v}"' for k, v in attrs)
        self.output.append(f'<{tag}{attrs_str}/>')

    def handle_data(self, data):
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
                escaped = part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

                # Check if this matches the current raw token
                if self._token_matches(part) and self.current_raw_token is not None:
                    # Wrap with span using the raw token index
                    idx = self.current_raw_token.index
                    result.append(f'<span class="word" data-word-index="{idx}">{escaped}</span>')
                    self._advance_token()
                else:
                    # No matching token - output as-is (shouldn't happen normally)
                    result.append(escaped)

        self.output.append(''.join(result))

    def handle_entityref(self, name):
        """Handle HTML entity references like &amp;."""
        self.output.append(f'&{name};')

    def handle_charref(self, name):
        """Handle HTML character references like &#39;."""
        self.output.append(f'&#{name};')

    def get_output(self) -> str:
        """Return the processed HTML output."""
        return ''.join(self.output)


def render_script_with_word_indices(script_text: str) -> Tuple[str, int, ParsedScript]:
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

    DEFAULT_SETTINGS = {
        "fontSize": 48,
        "fontFamily": "Georgia, serif",
        "lineHeight": 1.6,
        "pastLines": 1,
        "futureLines": 8,
        "theme": "dark",
        "highlightColor": "#FFD700",
        "textColor": "#FFFFFF",
        "dimColor": "#666666",
        "backgroundColor": "#1a1a1a"
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        initial_settings: Optional[dict] = None,
        samples_dir: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.websockets: Set[web.WebSocketResponse] = set()
        self.runner: Optional[web.AppRunner] = None

        # Sample scripts directory
        if samples_dir:
            self.samples_dir = Path(samples_dir)
        else:
            # Default to samples/ in the project root
            self.samples_dir = Path(__file__).parent.parent.parent / "samples"

        # Current state
        self.script_text: str = ""
        self.script_html: str = ""
        self.total_words: int = 0
        self._reset_requested: bool = False
        self._jump_requested: Optional[int] = None
        self._transcript_toggle_requested: Optional[bool] = None  # True=start, False=stop
        self._start_transcript_on_script: bool = False  # Start transcript when script loads

        # Merge initial settings with defaults
        self.settings = self.DEFAULT_SETTINGS.copy()
        if initial_settings:
            self.settings.update(initial_settings)

        self._setup_routes()

    def _get_sample_scripts(self) -> List[Dict[str, str]]:
        """Get list of available sample scripts."""
        samples = []
        if self.samples_dir.exists():
            for f in sorted(self.samples_dir.glob("*.md")):
                samples.append({
                    "name": f.stem.replace("_", " ").title(),
                    "filename": f.name
                })
        return samples

    def _load_sample_script(self, filename: str) -> Optional[str]:
        """Load a sample script by filename."""
        if not filename:
            return None
        # Sanitize filename to prevent path traversal
        safe_name = Path(filename).name
        script_path = self.samples_dir / safe_name
        if script_path.exists() and script_path.suffix == ".md":
            return script_path.read_text(encoding="utf-8")
        return None
        
    def _setup_routes(self):
        """Set up HTTP routes."""
        self.app.router.add_get('/', self._handle_index)
        self.app.router.add_get('/ws', self._handle_websocket)
        self.app.router.add_post('/script', self._handle_script_upload)
        self.app.router.add_post('/settings', self._handle_settings)
        self.app.router.add_get('/settings', self._handle_get_settings)
        self.app.router.add_post('/save-config', self._handle_save_config)
        self.app.router.add_get('/audio-devices', self._handle_get_audio_devices)
        
    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the main HTML page."""
        html = self._get_html()
        return web.Response(text=html, content_type='text/html')
        
    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time updates."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.websockets.add(ws)
        print(f"WebSocket connected. Total: {len(self.websockets)}")
        
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
                "audioDevice": config.get("audio_device")
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
        
    async def _handle_ws_message(self, ws: web.WebSocketResponse, data: dict):
        """Handle incoming WebSocket messages."""
        msg_type = data.get("type")
        
        if msg_type == "script":
            self.script_text = data.get("text", "")
            # Capture transcript preference - will be checked when script is loaded
            self._start_transcript_on_script = data.get("saveTranscript", False)
            # Render with word indices embedded in the HTML
            self.script_html, self.total_words, _ = render_script_with_word_indices(
                self.script_text
            )
            # Broadcast to all clients
            await self.broadcast({
                "type": "script_updated",
                "script": self.script_text,
                "scriptHtml": self.script_html,
                "totalWords": self.total_words
            })
            
        elif msg_type == "settings":
            self.settings.update(data.get("settings", {}))
            await self.broadcast({
                "type": "settings_updated",
                "settings": self.settings
            })
            
        elif msg_type == "reset":
            await self.broadcast({"type": "reset"})
            # Signal main app to reset tracker
            self._reset_requested = True

        elif msg_type == "jump_to":
            # User clicked to jump to a specific position
            word_index = data.get("wordIndex", 0)
            await self.broadcast({
                "type": "jump_to",
                "wordIndex": word_index
            })
            # Signal main app to jump tracker
            self._jump_requested = word_index

        elif msg_type == "save_config":
            # Save current settings to config file
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

        elif msg_type == "frontend_highlight":
            # Frontend reporting what word it's highlighting
            word_index = data.get("wordIndex", -1)
            word = data.get("word", "")
            source_line = data.get("sourceLine", -1)
            source_offset = data.get("sourceOffset", -1)
            server_word_index = data.get("serverWordIndex", -1)
            debug_log.log_frontend_word(word_index, word, source_line, source_offset)
            # Also log the raw server data
            debug_log.log_frontend_server_data(server_word_index, source_line, source_offset)

        elif msg_type == "load_sample":
            # Load a sample script by filename
            filename = data.get("filename", "")
            content = self._load_sample_script(filename)
            if content is not None:
                self.script_text = content
                self.script_html, self.total_words, _ = render_script_with_word_indices(
                    self.script_text
                )
                await self.broadcast({
                    "type": "script_updated",
                    "script": self.script_text,
                    "scriptHtml": self.script_html,
                    "totalWords": self.total_words
                })

        elif msg_type == "toggle_transcript":
            # Toggle transcript recording
            enable = data.get("enable", False)
            self._transcript_toggle_requested = enable

        elif msg_type == "set_audio_device":
            # Update audio device in config
            device_index = data.get("deviceIndex")
            try:
                config = load_config()
                config["audio_device"] = device_index
                if save_config(config):
                    await ws.send_json({
                        "type": "audio_device_updated",
                        "success": True,
                        "deviceIndex": device_index
                    })
                    # Broadcast to all clients
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
            
    async def _handle_script_upload(self, request: web.Request) -> web.Response:
        """Handle script upload via POST."""
        data = await request.json()
        self.script_text = data.get("text", "")
        # Render with word indices embedded in the HTML
        self.script_html, self.total_words, _ = render_script_with_word_indices(
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
            devices = sd.query_devices()
            device_list = []
            for i, device in enumerate(devices):
                dev: dict = dict(device)  # type: ignore[arg-type]
                if dev['max_input_channels'] > 0:
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

    async def broadcast(self, message: dict):
        """Send a message to all connected WebSocket clients."""
        if not self.websockets:
            return
            
        dead = set()
        for ws in self.websockets:
            try:
                await ws.send_json(message)
            except (ConnectionError, ConnectionResetError, RuntimeError) as e:
                print(f"Error sending to WebSocket: {e}")
                dead.add(ws)
                
        self.websockets -= dead
        
    async def send_transcript_status(self, recording: bool, file: Optional[str] = None):
        """Send transcript recording status to all clients."""
        await self.broadcast({
            "type": "transcript_status",
            "recording": recording,
            "file": str(file) if file else None
        })

    async def send_position(
        self,
        word_index: int,
        line_index: int,
        word_offset: int,
        confidence: float,
        is_backtrack: bool,
        transcript: str = ""
    ):
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
        
    async def start(self):
        """Start the web server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"Web server running at http://{self.host}:{self.port}")
        
    async def stop(self):
        """Stop the web server."""
        # Close all WebSocket connections
        for ws in list(self.websockets):
            try:
                await ws.close()
            except Exception:
                pass
        self.websockets.clear()

        if self.runner:
            await self.runner.cleanup()
            
    def _get_html(self) -> str:
        """Load and return the HTML for the autocue interface from static/index.html."""
        static_dir = Path(__file__).parent / "static"
        html_path = static_dir / "index.html"
        return html_path.read_text(encoding="utf-8")
