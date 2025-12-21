# Autocue

A low-latency teleprompter/autocue with local speech recognition. Paste your
script (with Markdown support), and the display scrolls automatically as you
speak—including detecting when you backtrack to restart a sentence.

## Note on AI-written code

The code was written almost entirely by Claude, with me prompting it for
improvements. While the implementation uses only local AI (speech recognition)
to do transcription, AI-generated code comes with other risks. I make no
promises about this code being production-worthy or safe. This is really just a
hobby project to support my own work on YouTube.

Use at your own risk / judgement.

Contributions are welcome. Contributions written by AI will be subject to equal
scrutiny.

## Platforms

I've written this for use on my Macbook Air M3. If it works on any other
platforms, that's a happy coincidence.

## Features

- **Sub-250ms latency** using Vosk streaming speech recognition
- **Backtrack detection** - automatically rewinds when you restart a sentence
- **Markdown support** - format your script for easy reading
- **Fully local & private** - no cloud services, all processing on your Mac
- **Configurable display** - font size, colors, line count, etc.
- **Web-based UI** - works on any browser, easy to put on a separate monitor

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4) or Intel
- Python 3.10+
- ~40MB for the small speech model (or ~1.8GB for medium)

## Installation

### 1. Install PortAudio (required for microphone access)

```bash
brew install portaudio
```

### 2. Install Autocue

```bash
# Clone or download this directory, then:
cd autocue
pip install -e .
```

### 3. Download the speech recognition model

```bash
autocue --download-model
```

This downloads the "small" model (~40MB). For better accuracy, use:
```bash
autocue --download-model --model medium
```

## Usage

### Start Autocue

```bash
autocue
```

Then open http://127.0.0.1:8765 in your browser.

### Workflow

1. **Paste your script** in the editor (left panel)
2. **Adjust settings** in the right panel (font size, colors, etc.)
3. **Click "Start Prompter"** to begin
4. **Speak** - the display tracks your position automatically
5. **Make a mistake?** Just restart your sentence - the prompter will detect the
   backtrack

### Keyboard Shortcuts (in prompter mode)

| Key | Action |
|-----|--------|
| `Escape` | Exit prompter mode |
| `Space` | Pause/resume tracking |
| `R` | Reset to start of script |

### Command Line Options

```
autocue --help

Options:
  --model, -m {small,medium,large}
                        Vosk model size (default: small)
  --model-path PATH     Path to custom Vosk model directory
  --host HOST           Web server host (default: 127.0.0.1)
  --port, -p PORT       Web server port (default: 8765)
  --device, -d INDEX    Audio input device index
  --list-devices        List available audio input devices
  --download-model      Download the specified model
  --chunk-ms MS         Audio chunk size in milliseconds (default: 100)
```

### Select a specific microphone

```bash
# List available microphones
autocue --list-devices

# Use a specific device (e.g., device 2)
autocue --device 2
```

### Access from another device on your network

```bash
autocue --host 0.0.0.0
```

Then access via your Mac's IP address from another device.

## Display Configuration

The settings panel lets you configure:

| Setting | Description |
|---------|-------------|
| **Font Size** | Text size in pixels (24-120) |
| **Font** | Choose from several readable fonts |
| **Line Height** | Spacing between lines |
| **Past Lines** | Lines of already-spoken text to show (default: 1) |
| **Future Lines** | Lines of upcoming text to show (default: 8) |
| **Colors** | Highlight, text, dim, and background colors |

## How It Works

1. **Audio Capture**: Your Mac's microphone captures audio in 100ms chunks
2. **Streaming Transcription**: Vosk processes audio in real-time, providing
   partial results as you speak (not waiting for complete sentences)
3. **Fuzzy Matching**: The tracker uses `rapidfuzz` to match transcribed text to
   your script, tolerating minor recognition errors
4. **Backtrack Detection**: If the matched position jumps backwards
   significantly, it's detected as a backtrack (you restarted a sentence)
5. **Web UI**: Updates are pushed via WebSocket to provide smooth, real-time
   scrolling

## Troubleshooting

### "Model not found" error

Run `autocue --download-model` to download the speech model.

### High latency

- Try the "small" model instead of "medium": `autocue --model small`
- Reduce chunk size: `autocue --chunk-ms 75`
- Close other applications using the microphone

### Poor recognition accuracy

- Try the "medium" model: `autocue --download-model --model medium`
- Ensure your microphone is positioned correctly
- Reduce background noise

### Microphone not detected

```bash
# List devices and check your microphone is present
autocue --list-devices

# Grant microphone permission to Terminal/your terminal app in System Preferences
```

### WebSocket connection issues

- Check that port 8765 is not in use by another application
- Try a different port: `autocue --port 8766`

## Model Comparison

| Model | Size | Accuracy | Latency | Recommended For |
|-------|------|----------|---------|-----------------|
| small | ~40MB | Good | Fastest | Most use cases |
| medium | ~1.8GB | Better | Fast | Noisy environments |
| large | ~2.3GB | Best | Slower | Maximum accuracy |
