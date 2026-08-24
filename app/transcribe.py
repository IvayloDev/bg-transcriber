"""Bulgarian speech to text with faster-whisper on CPU."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from . import config, models

StatusCb = Callable[[str], None]
ProgressCb = Callable[[float], None]


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    text: str
    segments: List[Segment] = field(default_factory=list)
    duration: float = 0.0
    language: str = "bg"


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(segments: List[Segment]) -> str:
    out = []
    for i, seg in enumerate(segments, 1):
        out.append(f"{i}\n{_ts(seg.start)} --> {_ts(seg.end)}\n{seg.text.strip()}\n")
    return "\n".join(out)


def transcribe(
    audio_path: str,
    size: str = config.DEFAULT_WHISPER,
    language: Optional[str] = "bg",
    status: Optional[StatusCb] = None,
    progress: Optional[ProgressCb] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Transcript:
    def say(msg: str):
        if status:
            status(msg)

    # Imported lazily so the window appears instantly on startup.
    from faster_whisper import WhisperModel

    model_dir = models.whisper_path(size)

    say(f"Зареждане на Whisper ({size})...")
    model = WhisperModel(
        str(model_dir),
        device="cpu",
        compute_type="int8",
        cpu_threads=0,
    )

    say("Разпознаване на речта...")
    seg_iter, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
    )

    duration = float(info.duration or 0.0)
    segments: List[Segment] = []
    parts: List[str] = []

    for seg in seg_iter:
        if should_stop and should_stop():
            raise KeyboardInterrupt("Спряно от потребителя")
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append(Segment(float(seg.start), float(seg.end), text))
        parts.append(text)
        if progress and duration > 0:
            progress(min(1.0, float(seg.end) / duration))

    if progress:
        progress(1.0)

    return Transcript(
        text=" ".join(parts).strip(),
        segments=segments,
        duration=duration,
        language=str(getattr(info, "language", language) or "bg"),
    )


def save_outputs(audio_path: str, tr: Transcript, out_dir: Optional[str] = None) -> dict:
    src = Path(audio_path)
    d = Path(out_dir) if out_dir else src.parent
    d.mkdir(parents=True, exist_ok=True)
    txt = d / f"{src.stem}_transcript.txt"
    srt = d / f"{src.stem}_transcript.srt"
    txt.write_text(tr.text, encoding="utf-8")
    srt.write_text(to_srt(tr.segments), encoding="utf-8")
    return {"txt": str(txt), "srt": str(srt)}
