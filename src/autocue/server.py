"""
Web server for the autocue interface.
Serves the HTML UI and handles WebSocket connections for real-time updates.
"""

import asyncio
import json
import logging
import os
import re
import markdown
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional, Set, List, Tuple, Dict
from aiohttp import web
import weakref

from .config import load_config, save_config, update_config_display
from . import debug_log
from .script_parser import (
    ParsedScript, parse_script, RawToken,
    PUNCTUATION_EXPANSIONS, is_silent_punctuation
)

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
        attrs_str = ''.join(f' {k}="{v}"' for k, v in attrs)
        self.output.append(f'<{tag}{attrs_str}>')
        self.tag_stack.append(tag)

    def handle_endtag(self, tag):
        self.output.append(f'</{tag}>')
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()

    def handle_startendtag(self, tag, attrs):
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
                if self._token_matches(part):
                    # Wrap with span using the raw token index
                    idx = self.current_raw_token.index
                    result.append(f'<span class="word" data-word-index="{idx}">{escaped}</span>')
                    self._advance_token()
                else:
                    # No matching token - output as-is (shouldn't happen normally)
                    result.append(escaped)

        self.output.append(''.join(result))

    def handle_entityref(self, name):
        self.output.append(f'&{name};')

    def handle_charref(self, name):
        self.output.append(f'&#{name};')

    def get_output(self) -> str:
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
        initial_settings: Optional[dict] = None
    ):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.websockets: Set[web.WebSocketResponse] = set()
        self.runner: Optional[web.AppRunner] = None

        # Current state
        self.script_text: str = ""
        self.script_html: str = ""
        self.total_words: int = 0
        self._reset_requested: bool = False
        self._jump_requested: Optional[int] = None

        # Merge initial settings with defaults
        self.settings = self.DEFAULT_SETTINGS.copy()
        if initial_settings:
            self.settings.update(initial_settings)

        self._setup_routes()
        
    def _setup_routes(self):
        """Set up HTTP routes."""
        self.app.router.add_get('/', self._handle_index)
        self.app.router.add_get('/ws', self._handle_websocket)
        self.app.router.add_post('/script', self._handle_script_upload)
        self.app.router.add_post('/settings', self._handle_settings)
        self.app.router.add_get('/settings', self._handle_get_settings)
        self.app.router.add_post('/save-config', self._handle_save_config)
        
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
            await ws.send_json({
                "type": "init",
                "script": self.script_text,
                "scriptHtml": self.script_html,
                "totalWords": self.total_words,
                "settings": self.settings
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
        
    async def broadcast(self, message: dict):
        """Send a message to all connected WebSocket clients."""
        if not self.websockets:
            return
            
        dead = set()
        for ws in self.websockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                print(f"Error sending to WebSocket: {e}")
                dead.add(ws)
                
        self.websockets -= dead
        
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
        """Generate the HTML for the autocue interface."""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autocue</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;600&family=Inter:wght@400;500;600&family=Playfair+Display:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --font-size: 48px;
            --font-family: "Crimson Pro", Georgia, serif;
            --line-height: 1.6;
            --text-color: #FFFFFF;
            --dim-color: #555555;
            --highlight-color: #FFD700;
            --bg-color: #0a0a0a;
            --past-lines: 1;
        }
        
        body {
            font-family: var(--font-family);
            font-size: var(--font-size);
            line-height: var(--line-height);
            background-color: var(--bg-color);
            color: var(--text-color);
            overflow: hidden;
            height: 100vh;
            transition: background-color 0.3s ease;
        }
        
        /* Editor Mode */
        #editor-container {
            display: flex;
            height: 100vh;
            background: #111;
        }
        
        #editor-panel {
            flex: 1;
            padding: 24px;
            display: flex;
            flex-direction: column;
            border-right: 1px solid #333;
        }
        
        #settings-panel {
            width: 320px;
            padding: 24px;
            overflow-y: auto;
            background: #0d0d0d;
        }
        
        #script-input {
            flex: 1;
            width: 100%;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            color: #fff;
            font-family: "Inter", sans-serif;
            font-size: 16px;
            line-height: 1.6;
            padding: 20px;
            resize: none;
            outline: none;
        }
        
        #script-input:focus {
            border-color: #555;
        }
        
        #script-input::placeholder {
            color: #666;
        }
        
        .editor-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        
        .editor-title {
            font-family: "Inter", sans-serif;
            font-size: 14px;
            font-weight: 600;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .btn {
            font-family: "Inter", sans-serif;
            font-size: 14px;
            font-weight: 500;
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .btn-primary {
            background: #FFD700;
            color: #000;
        }
        
        .btn-primary:hover {
            background: #FFED4A;
            transform: translateY(-1px);
        }
        
        .btn-secondary {
            background: #333;
            color: #fff;
        }
        
        .btn-secondary:hover {
            background: #444;
        }
        
        .settings-section {
            margin-bottom: 28px;
        }
        
        .settings-title {
            font-family: "Inter", sans-serif;
            font-size: 11px;
            font-weight: 600;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 14px;
        }
        
        .setting-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }
        
        .setting-label {
            font-family: "Inter", sans-serif;
            font-size: 13px;
            color: #aaa;
        }
        
        .setting-input {
            width: 80px;
            padding: 6px 10px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 4px;
            color: #fff;
            font-family: "Inter", sans-serif;
            font-size: 13px;
            text-align: right;
        }
        
        .setting-select {
            padding: 6px 10px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 4px;
            color: #fff;
            font-family: "Inter", sans-serif;
            font-size: 13px;
        }
        
        .color-input {
            width: 50px;
            height: 30px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        
        /* Prompter Mode */
        #prompter-container {
            display: none;
            height: 100vh;
            flex-direction: column;
            justify-content: flex-start;
            padding: 5vh 10vw;
            position: relative;
            overflow-y: auto;
        }

        #prompter-container.active {
            display: flex;
        }

        #script-display {
            max-height: 80vh;
            overflow-y: auto;
            padding-bottom: 40vh;
        }

        #script-display p {
            margin: 0.3em 0;
        }
        
        #editor-container.hidden {
            display: none;
        }
        
        .script-line {
            transition: all 0.15s ease-out;
            padding: 0.1em 0;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .script-line.past {
            color: var(--dim-color);
            opacity: 0.5;
        }
        
        .script-line.current {
            color: var(--highlight-color);
            font-weight: 600;
        }
        
        .script-line.future {
            color: var(--text-color);
        }
        
        .word {
            display: inline;
            transition: color 0.1s ease;
            cursor: pointer;
        }

        .word:hover {
            text-decoration: underline;
            text-underline-offset: 4px;
        }

        .word.spoken {
            color: var(--dim-color);
        }

        .word.current {
            color: var(--highlight-color);
            text-decoration: underline;
            text-underline-offset: 4px;
        }

        /* Markdown styles for prompter */
        #script-display h1,
        #script-display h2,
        #script-display h3,
        #script-display h4,
        #script-display h5,
        #script-display h6 {
            margin: 0.3em 0;
            font-weight: 600;
        }

        #script-display h1 { font-size: 1.4em; }
        #script-display h2 { font-size: 1.25em; }
        #script-display h3 { font-size: 1.1em; }

        #script-display strong,
        #script-display b {
            font-weight: 600;
        }

        #script-display em,
        #script-display i {
            font-style: italic;
        }

        #script-display ul,
        #script-display ol {
            margin: 0.2em 0;
            padding-left: 1.5em;
        }

        #script-display li {
            margin: 0.1em 0;
        }

        #script-display blockquote {
            border-left: 3px solid var(--highlight-color);
            padding-left: 0.8em;
            margin: 0.3em 0;
            opacity: 0.9;
        }

        #script-display code {
            font-family: monospace;
            background: rgba(255, 255, 255, 0.1);
            padding: 0.1em 0.3em;
            border-radius: 3px;
        }

        #script-display hr {
            border: none;
            border-top: 1px solid var(--dim-color);
            margin: 0.5em 0;
        }

        /* Progress bar */
        #progress-bar {
            position: fixed;
            bottom: 0;
            left: 0;
            height: 4px;
            background: var(--highlight-color);
            transition: width 0.2s ease;
            opacity: 0.8;
        }
        
        /* Status indicator */
        #status {
            position: fixed;
            top: 20px;
            right: 20px;
            font-family: "Inter", sans-serif;
            font-size: 12px;
            padding: 8px 14px;
            background: rgba(0,0,0,0.7);
            border-radius: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #666;
        }
        
        .status-dot.listening {
            background: #4CAF50;
            animation: pulse 1.5s infinite;
        }
        
        .status-dot.backtrack {
            background: #FF9800;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        /* Exit button */
        #exit-btn {
            position: fixed;
            top: 20px;
            left: 20px;
            font-family: "Inter", sans-serif;
            font-size: 12px;
            padding: 8px 14px;
            background: rgba(255,255,255,0.1);
            border: none;
            border-radius: 20px;
            color: #888;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        #exit-btn:hover {
            background: rgba(255,255,255,0.2);
            color: #fff;
        }
        
        /* Transcript display */
        #transcript {
            position: fixed;
            bottom: 20px;
            left: 20px;
            right: 20px;
            font-family: "Inter", sans-serif;
            font-size: 14px;
            color: #666;
            text-align: center;
            max-height: 60px;
            overflow: hidden;
        }
    </style>
</head>
<body>
    <!-- Editor Mode -->
    <div id="editor-container">
        <div id="editor-panel">
            <div class="editor-header">
                <span class="editor-title">Script (Markdown supported)</span>
                <button class="btn btn-primary" onclick="startPrompter()">Start Prompter</button>
            </div>
            <textarea id="script-input" placeholder="Paste your script here...

You can use **Markdown** formatting:
- Headers with # 
- **Bold** and *italic*
- Lists and paragraphs

The prompter will track your speech and scroll automatically."></textarea>
        </div>
        
        <div id="settings-panel">
            <div class="settings-section">
                <div class="settings-title">Typography</div>
                <div class="setting-row">
                    <span class="setting-label">Font Size</span>
                    <input type="number" class="setting-input" id="setting-fontSize" value="48" min="24" max="120">
                </div>
                <div class="setting-row">
                    <span class="setting-label">Font</span>
                    <select class="setting-select" id="setting-fontFamily">
                        <option value='"Crimson Pro", Georgia, serif'>Crimson Pro</option>
                        <option value='"Playfair Display", Georgia, serif'>Playfair Display</option>
                        <option value='Georgia, serif'>Georgia</option>
                        <option value='"Inter", sans-serif'>Inter</option>
                        <option value='system-ui, sans-serif'>System</option>
                    </select>
                </div>
                <div class="setting-row">
                    <span class="setting-label">Line Height</span>
                    <input type="number" class="setting-input" id="setting-lineHeight" value="1.6" min="1" max="3" step="0.1">
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title">Display</div>
                <div class="setting-row">
                    <span class="setting-label">Past Lines</span>
                    <input type="number" class="setting-input" id="setting-pastLines" value="1" min="0" max="5">
                </div>
                <div class="setting-row">
                    <span class="setting-label">Future Lines</span>
                    <input type="number" class="setting-input" id="setting-futureLines" value="8" min="3" max="20">
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title">Colors</div>
                <div class="setting-row">
                    <span class="setting-label">Highlight</span>
                    <input type="color" class="color-input" id="setting-highlightColor" value="#FFD700">
                </div>
                <div class="setting-row">
                    <span class="setting-label">Text</span>
                    <input type="color" class="color-input" id="setting-textColor" value="#FFFFFF">
                </div>
                <div class="setting-row">
                    <span class="setting-label">Dim</span>
                    <input type="color" class="color-input" id="setting-dimColor" value="#555555">
                </div>
                <div class="setting-row">
                    <span class="setting-label">Background</span>
                    <input type="color" class="color-input" id="setting-backgroundColor" value="#0a0a0a">
                </div>
            </div>
            
            <div class="settings-section">
                <div class="settings-title">Keyboard Shortcuts</div>
                <div class="setting-row">
                    <span class="setting-label" style="color: #666;">Escape</span>
                    <span class="setting-label">Exit prompter</span>
                </div>
                <div class="setting-row">
                    <span class="setting-label" style="color: #666;">Space</span>
                    <span class="setting-label">Pause/Resume</span>
                </div>
                <div class="setting-row">
                    <span class="setting-label" style="color: #666;">R</span>
                    <span class="setting-label">Reset to start</span>
                </div>
            </div>

            <div class="settings-section">
                <button class="btn btn-secondary" id="save-config-btn" onclick="saveConfig()" style="width: 100%;">Save as Default</button>
                <div id="save-status" style="font-family: 'Inter', sans-serif; font-size: 12px; color: #666; margin-top: 8px; text-align: center;"></div>
            </div>
        </div>
    </div>
    
    <!-- Prompter Mode -->
    <div id="prompter-container">
        <div id="script-display"></div>
        <div id="progress-bar" style="width: 0%"></div>
        <div id="status">
            <span class="status-dot listening"></span>
            <span id="status-text">Listening...</span>
        </div>
        <button id="exit-btn" onclick="exitPrompter()">← Exit</button>
        <div id="transcript"></div>
    </div>

    <script>
        let ws = null;
        let totalWords = 0;  // Set by server
        let currentWordIndex = 0;
        let settings = {};
        let isPaused = false;
        let scriptHtml = '';  // Pre-indexed HTML from server
        
        // Connect WebSocket
        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => console.log('WebSocket connected');
            ws.onclose = () => {
                console.log('WebSocket disconnected, reconnecting...');
                setTimeout(connect, 1000);
            };
            ws.onerror = (e) => console.error('WebSocket error:', e);
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleMessage(data);
            };
        }
        
        function handleMessage(data) {
            switch (data.type) {
                case 'init':
                    document.getElementById('script-input').value = data.script || '';
                    scriptHtml = data.scriptHtml || '';
                    totalWords = data.totalWords || 0;
                    settings = data.settings || {};
                    applySettings(settings);
                    break;

                case 'script_updated':
                    document.getElementById('script-input').value = data.script;
                    scriptHtml = data.scriptHtml || '';
                    totalWords = data.totalWords || 0;
                    // If we were waiting to start the prompter, do it now
                    if (waitingForScript) {
                        waitingForScript = false;
                        activatePrompterMode();
                    }
                    break;
                    
                case 'settings_updated':
                    settings = data.settings;
                    applySettings(settings);
                    break;
                    
                case 'position':
                    updatePosition(data);
                    break;
                    
                case 'reset':
                    resetDisplay();
                    break;

                case 'jump_to':
                    jumpToWord(data.wordIndex);
                    break;

                case 'config_saved':
                    const statusEl = document.getElementById('save-status');
                    if (data.success) {
                        statusEl.textContent = 'Settings saved!';
                        statusEl.style.color = '#4CAF50';
                    } else {
                        statusEl.textContent = 'Failed to save: ' + (data.error || 'Unknown error');
                        statusEl.style.color = '#f44336';
                    }
                    setTimeout(() => { statusEl.textContent = ''; }, 3000);
                    break;
            }
        }
        
        function applySettings(s) {
            const root = document.documentElement;
            root.style.setProperty('--font-size', s.fontSize + 'px');
            root.style.setProperty('--font-family', s.fontFamily);
            root.style.setProperty('--line-height', s.lineHeight);
            root.style.setProperty('--highlight-color', s.highlightColor);
            root.style.setProperty('--text-color', s.textColor);
            root.style.setProperty('--dim-color', s.dimColor);
            root.style.setProperty('--bg-color', s.backgroundColor);
            
            // Update input values
            for (const [key, value] of Object.entries(s)) {
                const el = document.getElementById('setting-' + key);
                if (el) el.value = value;
            }
        }
        
        function getSettings() {
            return {
                fontSize: parseInt(document.getElementById('setting-fontSize').value),
                fontFamily: document.getElementById('setting-fontFamily').value,
                lineHeight: parseFloat(document.getElementById('setting-lineHeight').value),
                pastLines: parseInt(document.getElementById('setting-pastLines').value),
                futureLines: parseInt(document.getElementById('setting-futureLines').value),
                highlightColor: document.getElementById('setting-highlightColor').value,
                textColor: document.getElementById('setting-textColor').value,
                dimColor: document.getElementById('setting-dimColor').value,
                backgroundColor: document.getElementById('setting-backgroundColor').value
            };
        }

        function saveConfig() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const statusEl = document.getElementById('save-status');
                statusEl.textContent = 'Saving...';
                statusEl.style.color = '#666';
                ws.send(JSON.stringify({ type: 'save_config' }));
            }
        }

        // Flag to indicate we're waiting for server to send indexed HTML
        let waitingForScript = false;

        function startPrompter() {
            const script = document.getElementById('script-input').value.trim();
            if (!script) {
                alert('Please enter a script first');
                return;
            }

            // Send script and settings to server
            // The server will respond with indexed HTML in script_updated message
            settings = getSettings();
            waitingForScript = true;
            ws.send(JSON.stringify({ type: 'script', text: script }));
            ws.send(JSON.stringify({ type: 'settings', settings: settings }));
        }

        function activatePrompterMode() {
            // Switch to prompter mode
            document.getElementById('editor-container').classList.add('hidden');
            document.getElementById('prompter-container').classList.add('active');

            // Initial render using server-provided indexed HTML
            currentWordIndex = 0;
            renderScriptByWordIndex(0);

            // Apply settings
            applySettings(settings);
        }

        function exitPrompter() {
            document.getElementById('editor-container').classList.remove('hidden');
            document.getElementById('prompter-container').classList.remove('active');
        }

        function renderScriptByWordIndex(wordIndex) {
            const display = document.getElementById('script-display');

            // Render the pre-indexed HTML from server
            display.innerHTML = scriptHtml;

            // Update word styling based on current position
            display.querySelectorAll('.word').forEach(el => {
                const wordIdx = parseInt(el.dataset.wordIndex, 10);
                el.classList.remove('spoken', 'current');

                if (wordIdx < wordIndex) {
                    el.classList.add('spoken');
                } else if (wordIdx === wordIndex) {
                    el.classList.add('current');
                }

                // Add click handler
                el.addEventListener('click', handleWordClick);
            });

            // Scroll the current word into view
            const currentEl = display.querySelector('.word.current');
            if (currentEl) {
                currentEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }

        function handleWordClick(e) {
            const wordIndex = parseInt(e.target.dataset.wordIndex, 10);
            if (!isNaN(wordIndex)) {
                ws.send(JSON.stringify({ type: 'jump_to', wordIndex: wordIndex }));
            }
        }

        function jumpToWord(wordIndex) {
            currentWordIndex = wordIndex;
            renderScriptByWordIndex(wordIndex);

            // Update progress bar
            const progress = totalWords > 0 ? (wordIndex / totalWords) * 100 : 0;
            document.getElementById('progress-bar').style.width = progress + '%';
        }

        function updatePosition(data) {
            if (isPaused) return;

            // Use wordIndex directly - no line/offset conversion needed
            // since we use server-provided word indices in the HTML
            currentWordIndex = data.wordIndex;
            renderScriptByWordIndex(data.wordIndex);

            // Report what word we're highlighting back to server for debugging
            const currentEl = document.querySelector('.word.current');
            if (currentEl && ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'frontend_highlight',
                    wordIndex: data.wordIndex,
                    word: currentEl.textContent,
                    sourceLine: data.lineIndex,
                    sourceOffset: data.wordOffset,
                    serverWordIndex: data.wordIndex
                }));
            }

            // Update progress bar
            const progress = totalWords > 0 ? (data.wordIndex / totalWords) * 100 : 0;
            document.getElementById('progress-bar').style.width = progress + '%';

            // Update status
            const dot = document.querySelector('.status-dot');
            const statusText = document.getElementById('status-text');

            if (data.isBacktrack) {
                dot.className = 'status-dot backtrack';
                statusText.textContent = 'Backtrack detected';
                setTimeout(() => {
                    dot.className = 'status-dot listening';
                    statusText.textContent = 'Listening...';
                }, 1000);
            } else if (data.confidence > 70) {
                dot.className = 'status-dot listening';
                statusText.textContent = 'Listening...';
            }

            // Show transcript
            if (data.transcript) {
                document.getElementById('transcript').textContent = data.transcript;
            }
        }

        function resetDisplay() {
            currentWordIndex = 0;
            renderScriptByWordIndex(0);
            document.getElementById('progress-bar').style.width = '0%';
        }
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (!document.getElementById('prompter-container').classList.contains('active')) {
                return;
            }
            
            switch (e.key) {
                case 'Escape':
                    exitPrompter();
                    break;
                case ' ':
                    e.preventDefault();
                    isPaused = !isPaused;
                    document.getElementById('status-text').textContent = isPaused ? 'Paused' : 'Listening...';
                    break;
                case 'r':
                case 'R':
                    ws.send(JSON.stringify({ type: 'reset' }));
                    resetDisplay();
                    break;
            }
        });
        
        // Settings change handlers
        document.querySelectorAll('#settings-panel input, #settings-panel select').forEach(el => {
            el.addEventListener('change', () => {
                const newSettings = getSettings();
                applySettings(newSettings);
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'settings', settings: newSettings }));
                }
            });
        });
        
        // Initialize
        connect();
    </script>
</body>
</html>'''
