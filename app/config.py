"""Paths, model choices and shared constants."""

import os
import sys
from pathlib import Path

APP_NAME = "BG Transcriber"
APP_DIR_NAME = "BGTranscriber"

# Whisper (CTranslate2) checkpoints on the Hugging Face hub.
# int8 on CPU is the only sane option on a laptop without a GPU.
WHISPER_MODELS = {
    "small": {
        "repo": "Systran/faster-whisper-small",
        "label": "small - fastest, roughest Bulgarian (~0.5 GB)",
        "approx_bytes": 500_000_000,
    },
    "medium": {
        "repo": "Systran/faster-whisper-medium",
        "label": "medium - balanced, recommended (~1.5 GB)",
        "approx_bytes": 1_600_000_000,
    },
    "large-v3": {
        "repo": "Systran/faster-whisper-large-v3",
        "label": "large-v3 - best quality, very slow on CPU (~3 GB)",
        "approx_bytes": 3_200_000_000,
    },
}
DEFAULT_WHISPER = "medium"

# Summary model. Gemma 3 4B has genuinely usable Bulgarian and fits in RAM.
LLM_REPO = "unsloth/gemma-3-4b-it-GGUF"
LLM_FILE = "gemma-3-4b-it-Q4_K_M.gguf"
LLM_APPROX_BYTES = 2_500_000_000

LLM_CTX = 8192
# Roughly 2.5 characters per token for Cyrillic, so keep map chunks modest.
MAP_CHUNK_CHARS = 6000


def data_dir() -> Path:
    """Per-user writable directory for models and settings."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".local" / "share"
    d = root / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path() -> Path:
    return data_dir() / "settings.json"


def bundle_dir() -> Path:
    """Directory the app is running from, PyInstaller aware."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


AUDIO_EXTS = [
    ".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac",
    ".flac", ".wma", ".mp4", ".mkv", ".mov", ".webm",
]
