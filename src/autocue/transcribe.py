"""
Speech transcription module using Vosk for low-latency streaming recognition.
Provides partial results as speech is happening, not just final results.
"""

import json
import os
from pathlib import Path
from typing import Callable, Optional, Tuple
from vosk import Model, KaldiRecognizer, SetLogLevel


# Suppress Vosk's verbose logging
SetLogLevel(-1)


class TranscriptionResult:
    """Represents a transcription result from Vosk."""
    
    def __init__(self, text: str, is_partial: bool, confidence: float = 1.0):
        self.text = text
        self.is_partial = is_partial
        self.confidence = confidence
        
    def __repr__(self):
        status = "partial" if self.is_partial else "final"
        return f"TranscriptionResult({status}: '{self.text}')"


class Transcriber:
    """
    Streaming speech transcriber using Vosk.
    
    Vosk is designed for real-time streaming and provides:
    - Partial results while speaking (low latency)
    - Final results when speech pauses
    - Runs entirely locally
    """
    
    # Model download URLs and names
    MODELS = {
        "small": "vosk-model-small-en-us-0.15",  # ~40MB, fastest
        "medium": "vosk-model-en-us-0.22",        # ~1.8GB, better accuracy
        "large": "vosk-model-en-us-0.42-gigaspeech",  # ~2.3GB, best accuracy
    }
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        model_name: str = "small",
        sample_rate: int = 16000
    ):
        """
        Initialize the transcriber.
        
        Args:
            model_path: Path to Vosk model directory, or None to auto-download
            model_name: One of "small", "medium", "large" if model_path is None
            sample_rate: Audio sample rate (must match audio capture)
        """
        self.sample_rate = sample_rate
        self.model_path = model_path or self._get_model_path(model_name)
        
        print(f"Loading Vosk model from: {self.model_path}")
        if not os.path.exists(self.model_path):
            raise RuntimeError(
                f"Model not found at {self.model_path}. "
                f"Please download from https://alphacephei.com/vosk/models "
                f"and extract to this path, or run 'autocue --download-model'"
            )
            
        self.model = Model(self.model_path)
        self.recognizer = KaldiRecognizer(self.model, sample_rate)
        self.recognizer.SetWords(True)  # Include word-level timing
        
    def _get_model_path(self, model_name: str) -> str:
        """Get the default model path for the given model name."""
        # Store models in user's cache directory
        cache_dir = Path.home() / ".cache" / "autocue" / "models"
        model_dir_name = self.MODELS.get(model_name, model_name)
        return str(cache_dir / model_dir_name)
        
    def process_audio(self, audio_data: bytes) -> Optional[TranscriptionResult]:
        """
        Process an audio chunk and return transcription result.
        
        Args:
            audio_data: Raw audio bytes (16-bit PCM, mono)
            
        Returns:
            TranscriptionResult with partial or final text, or None if no speech
        """
        if self.recognizer.AcceptWaveform(audio_data):
            # Final result - speech segment complete
            result = json.loads(self.recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                return TranscriptionResult(text, is_partial=False)
        else:
            # Partial result - speech still in progress
            result = json.loads(self.recognizer.PartialResult())
            text = result.get("partial", "").strip()
            if text:
                return TranscriptionResult(text, is_partial=True)
                
        return None
        
    def reset(self):
        """Reset the recognizer state (e.g., after a long pause)."""
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
        self.recognizer.SetWords(True)
        
    def get_final(self) -> Optional[TranscriptionResult]:
        """Get any remaining buffered speech as final result."""
        result = json.loads(self.recognizer.FinalResult())
        text = result.get("text", "").strip()
        if text:
            return TranscriptionResult(text, is_partial=False)
        return None


def download_model(model_name: str = "small", target_dir: Optional[str] = None):
    """
    Download a Vosk model.
    
    Args:
        model_name: One of "small", "medium", "large"
        target_dir: Directory to save the model, or None for default
    """
    import urllib.request
    import zipfile
    import tempfile
    
    model_dir_name = Transcriber.MODELS.get(model_name)
    if not model_dir_name:
        raise ValueError(f"Unknown model: {model_name}. Choose from: {list(Transcriber.MODELS.keys())}")
    
    if target_dir is None:
        target_dir = Path.home() / ".cache" / "autocue" / "models"
    else:
        target_dir = Path(target_dir)
        
    target_dir.mkdir(parents=True, exist_ok=True)
    model_path = target_dir / model_dir_name
    
    if model_path.exists():
        print(f"Model already exists at {model_path}")
        return str(model_path)
    
    url = f"https://alphacephei.com/vosk/models/{model_dir_name}.zip"
    print(f"Downloading {model_name} model from {url}...")
    print("This may take a few minutes depending on your connection.")
    
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        urllib.request.urlretrieve(url, tmp.name)
        
        print("Extracting model...")
        with zipfile.ZipFile(tmp.name, 'r') as zf:
            zf.extractall(target_dir)
            
        os.unlink(tmp.name)
        
    print(f"Model installed to {model_path}")
    return str(model_path)
