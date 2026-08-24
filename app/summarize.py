"""Offline Bulgarian summarisation via llama.cpp (map-reduce over the transcript)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, List, Optional

from . import config, models

StatusCb = Callable[[str], None]
ProgressCb = Callable[[float], None]

MAP_PROMPT = """Ти си прецизен асистент. По-долу е част от транскрипция на аудиозапис на български език.

Обобщи тази част в кратки точки на български. Запази всички факти, имена, числа, дати, решения и поети ангажименти. Не измисляй нищо. Не добавяй увод или заключение.

ЧАСТ ОТ ТРАНСКРИПЦИЯТА:
{chunk}

ТОЧКИ:"""

REDUCE_PROMPT = """Ти си прецизен асистент. По-долу са бележки от последователни части на един аудиозапис на български език.

Напиши цялостно резюме на български със следната структура и точно тези заглавия:

## Кратко резюме
Три до пет изречения по същество.

## Основни теми
Точки с най-важното обсъдено.

## Решения
Какво е решено. Ако няма, напиши "Няма изрични решения."

## Задачи и следващи стъпки
Кой какво поема. Ако няма, напиши "Няма конкретни задачи."

## Отворени въпроси
Каквото е останало нерешено. Ако няма, напиши "Няма."

Не измисляй факти. Използвай само информацията от бележките.

БЕЛЕЖКИ:
{notes}

РЕЗЮМЕ:"""


def _split(text: str, limit: int = config.MAP_CHUNK_CHARS) -> List[str]:
    """Split on sentence boundaries, packing up to `limit` characters per chunk."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        while len(s) > limit:  # a single runaway sentence
            chunks.append(s[:limit])
            s = s[limit:]
        if len(cur) + len(s) + 1 > limit and cur:
            chunks.append(cur.strip())
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


class Summarizer:
    def __init__(self, status: Optional[StatusCb] = None):
        self._status = status
        self._llm = None

    def _say(self, msg: str):
        if self._status:
            self._status(msg)

    def _load(self):
        if self._llm is not None:
            return self._llm
        from llama_cpp import Llama

        path = models.llm_path()
        self._say("Зареждане на модела за резюме...")
        self._llm = Llama(
            model_path=str(path),
            n_ctx=config.LLM_CTX,
            n_threads=max(1, (os.cpu_count() or 4) - 1),
            n_batch=512,
            verbose=False,
        )
        return self._llm

    def _ask(self, prompt: str, max_tokens: int) -> str:
        llm = self._load()
        out = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.2,
            top_p=0.9,
        )
        return (out["choices"][0]["message"]["content"] or "").strip()

    def close(self):
        if self._llm is not None:
            try:
                self._llm.close()
            except Exception:
                pass
            self._llm = None

    def summarize(
        self,
        transcript: str,
        progress: Optional[ProgressCb] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> str:
        def stop_check():
            if should_stop and should_stop():
                raise KeyboardInterrupt("Спряно от потребителя")

        chunks = _split(transcript)
        if not chunks:
            return "Транскрипцията е празна."

        stop_check()

        if len(chunks) == 1:
            self._say("Съставяне на резюме...")
            result = self._ask(REDUCE_PROMPT.format(notes=chunks[0]), 1200)
            if progress:
                progress(1.0)
            return result

        notes: List[str] = []
        for i, chunk in enumerate(chunks, 1):
            stop_check()
            self._say(f"Обобщаване на част {i} от {len(chunks)}...")
            notes.append(self._ask(MAP_PROMPT.format(chunk=chunk), 500))
            if progress:
                progress(0.85 * i / len(chunks))

        joined = "\n\n".join(notes)
        # Collapse repeatedly until the notes fit comfortably in one pass.
        while len(joined) > config.MAP_CHUNK_CHARS * 1.5:
            stop_check()
            self._say("Уплътняване на бележките...")
            groups = _split(joined)
            joined = "\n\n".join(self._ask(MAP_PROMPT.format(chunk=g), 500) for g in groups)

        stop_check()
        self._say("Съставяне на финално резюме...")
        result = self._ask(REDUCE_PROMPT.format(notes=joined), 1200)
        if progress:
            progress(1.0)
        return result


def save_summary(audio_path: str, summary: str, out_dir: Optional[str] = None) -> str:
    src = Path(audio_path)
    d = Path(out_dir) if out_dir else src.parent
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{src.stem}_summary.txt"
    p.write_text(summary, encoding="utf-8")
    return str(p)
