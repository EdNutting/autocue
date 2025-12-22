"""
Autocue - Low-latency teleprompter with local speech recognition.

A teleprompter application that uses local AI (Vosk) to track your speech
and automatically scroll through your script in real-time.
"""

__version__ = "0.1.0"

from .audio import AudioCapture, list_devices
from .main import AutocueApp
from .server import WebServer
from .tracker import ScriptTracker
from .transcribe import Transcriber, download_model

__all__ = [
    "AudioCapture",
    "list_devices",
    "Transcriber",
    "download_model",
    "ScriptTracker",
    "WebServer",
    "AutocueApp",
]
