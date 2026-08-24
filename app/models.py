"""First-run model downloads with real byte progress."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from huggingface_hub import snapshot_download
from tqdm import tqdm as _tqdm

from . import config

ProgressCb = Callable[[int, int, str], None]

_lock = threading.Lock()
_live: list["_HookTqdm"] = []
_callback: Optional[ProgressCb] = None
_label = ""


class _HookTqdm(_tqdm):
    """tqdm subclass that reports aggregate byte progress to a callback.

    huggingface_hub creates one bar per file plus a bar counting files, so we
    only sum the ones measured in bytes.
    """

    def __init__(self, *args, **kwargs):
        kwargs["disable"] = False
        kwargs["file"] = _NullStream()
        super().__init__(*args, **kwargs)
        if self.unit == "B":
            with _lock:
                _live.append(self)

    def update(self, n=1):
        out = super().update(n)
        if self.unit == "B":
            _emit()
        return out

    def close(self):
        if self.unit == "B":
            with _lock:
                if self in _live:
                    _live.remove(self)
            _emit()
        return super().close()


class _NullStream:
    def write(self, *_a, **_k):
        return 0

    def flush(self):
        pass


def _emit():
    cb = _callback
    if cb is None:
        return
    with _lock:
        done = sum(b.n for b in _live)
        total = sum(b.total or 0 for b in _live)
    cb(done, total, _label)


def _download(repo: str, label: str, allow=None, cb: Optional[ProgressCb] = None) -> Path:
    global _callback, _label
    _callback, _label = cb, label
    with _lock:
        _live.clear()
    try:
        path = snapshot_download(
            repo_id=repo,
            allow_patterns=allow,
            local_dir=str(config.models_dir() / repo.split("/")[-1]),
            tqdm_class=_HookTqdm,
        )
    finally:
        _callback, _label = None, ""
        with _lock:
            _live.clear()
    return Path(path)


def whisper_path(size: str, cb: Optional[ProgressCb] = None) -> Path:
    """Local directory holding the CTranslate2 Whisper checkpoint."""
    repo = config.WHISPER_MODELS[size]["repo"]
    return _download(repo, f"Изтегляне на Whisper ({size})", cb=cb)


def llm_path(cb: Optional[ProgressCb] = None) -> Path:
    """Local path to the summary model GGUF."""
    target = config.models_dir() / config.LLM_REPO.split("/")[-1] / config.LLM_FILE
    if target.exists() and target.stat().st_size > 1_000_000_000:
        return target
    _download(config.LLM_REPO, "Изтегляне на модел за резюме", allow=[config.LLM_FILE], cb=cb)
    if not target.exists():
        raise FileNotFoundError(f"Липсва файл след изтегляне: {target}")
    return target


def is_whisper_ready(size: str) -> bool:
    repo = config.WHISPER_MODELS[size]["repo"]
    d = config.models_dir() / repo.split("/")[-1]
    return (d / "model.bin").exists()


def is_llm_ready() -> bool:
    p = config.models_dir() / config.LLM_REPO.split("/")[-1] / config.LLM_FILE
    return p.exists() and p.stat().st_size > 1_000_000_000
