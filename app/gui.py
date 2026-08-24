"""Tkinter desktop UI. Bulgarian labels, everything runs on a worker thread."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, W, X, Y, filedialog, messagebox
import tkinter as tk
from tkinter import ttk

from . import config, models, summarize, transcribe

PAD = 10


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(config.APP_NAME)
        self.geometry("880x660")
        self.minsize(760, 560)

        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.audio_path = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.model_size = tk.StringVar(value=config.DEFAULT_WHISPER)
        self.do_summary = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Готов.")
        self._settings = self._load_settings()
        self.model_size.set(self._settings.get("model_size", config.DEFAULT_WHISPER))
        self.do_summary.set(self._settings.get("do_summary", True))

        self._build()
        self.after(100, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- settings ----------

    def _load_settings(self) -> dict:
        try:
            return json.loads(config.settings_path().read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        try:
            config.settings_path().write_text(
                json.dumps(
                    {"model_size": self.model_size.get(), "do_summary": self.do_summary.get()},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ---------- layout ----------

    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            pass

        top = ttk.Frame(self, padding=PAD)
        top.pack(fill=X)

        ttk.Label(top, text="Аудио файл:").grid(row=0, column=0, sticky=W, pady=4)
        ttk.Entry(top, textvariable=self.audio_path).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Избери...", command=self._pick_audio).grid(row=0, column=2)

        ttk.Label(top, text="Папка за запис:").grid(row=1, column=0, sticky=W, pady=4)
        ttk.Entry(top, textvariable=self.out_dir).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Избери...", command=self._pick_out).grid(row=1, column=2)

        ttk.Label(top, text="Модел:").grid(row=2, column=0, sticky=W, pady=4)
        combo = ttk.Combobox(
            top,
            state="readonly",
            values=[config.WHISPER_MODELS[k]["label"] for k in config.WHISPER_MODELS],
        )
        combo.grid(row=2, column=1, sticky="ew", padx=6)
        combo.set(config.WHISPER_MODELS[self.model_size.get()]["label"])
        combo.bind("<<ComboboxSelected>>", lambda e: self._on_model(combo.get()))
        self.combo = combo

        ttk.Checkbutton(top, text="Направи и резюме", variable=self.do_summary).grid(
            row=2, column=2, sticky=W
        )
        top.columnconfigure(1, weight=1)

        actions = ttk.Frame(self, padding=(PAD, 0, PAD, PAD))
        actions.pack(fill=X)
        self.btn_start = ttk.Button(actions, text="Старт", command=self._start)
        self.btn_start.pack(side=LEFT)
        self.btn_stop = ttk.Button(actions, text="Спри", command=self._stop, state="disabled")
        self.btn_stop.pack(side=LEFT, padx=6)
        ttk.Button(actions, text="Отвори папката", command=self._open_out).pack(side=RIGHT)

        prog = ttk.Frame(self, padding=(PAD, 0, PAD, PAD))
        prog.pack(fill=X)
        self.bar = ttk.Progressbar(prog, maximum=1000)
        self.bar.pack(fill=X)
        ttk.Label(prog, textvariable=self.status).pack(anchor=W, pady=(4, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill=BOTH, expand=True, padx=PAD, pady=(0, PAD))
        self.txt_transcript = self._text_tab(nb, "Транскрипция")
        self.txt_summary = self._text_tab(nb, "Резюме")

        bottom = ttk.Frame(self, padding=(PAD, 0, PAD, PAD))
        bottom.pack(fill=X)
        ttk.Button(bottom, text="Запази транскрипцията...", command=self._save_transcript).pack(side=LEFT)
        ttk.Button(bottom, text="Запази резюмето...", command=self._save_summary).pack(side=LEFT, padx=6)

    def _text_tab(self, nb: ttk.Notebook, title: str) -> tk.Text:
        frame = ttk.Frame(nb)
        nb.add(frame, text=title)
        txt = tk.Text(frame, wrap="word", undo=True, font=("Segoe UI", 10))
        scroll = ttk.Scrollbar(frame, command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        scroll.pack(side=RIGHT, fill=Y)
        txt.pack(side=LEFT, fill=BOTH, expand=True)
        return txt

    # ---------- ui events ----------

    def _on_model(self, label: str):
        for key, meta in config.WHISPER_MODELS.items():
            if meta["label"] == label:
                self.model_size.set(key)
                return

    def _pick_audio(self):
        pattern = " ".join(f"*{e}" for e in config.AUDIO_EXTS)
        path = filedialog.askopenfilename(
            title="Избери аудио файл",
            filetypes=[("Аудио и видео", pattern), ("Всички файлове", "*.*")],
        )
        if path:
            self.audio_path.set(path)
            if not self.out_dir.get():
                self.out_dir.set(str(Path(path).parent))

    def _pick_out(self):
        path = filedialog.askdirectory(title="Избери папка за запис")
        if path:
            self.out_dir.set(path)

    def _open_out(self):
        d = self.out_dir.get() or str(Path(self.audio_path.get()).parent if self.audio_path.get() else Path.home())
        if not Path(d).exists():
            return
        if sys.platform == "win32":
            os.startfile(d)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", d], check=False)
        else:
            subprocess.run(["xdg-open", d], check=False)

    def _save_transcript(self):
        self._save_text(self.txt_transcript, "_transcript.txt")

    def _save_summary(self):
        self._save_text(self.txt_summary, "_summary.txt")

    def _save_text(self, widget: tk.Text, suffix: str):
        content = widget.get("1.0", END).strip()
        if not content:
            messagebox.showinfo(config.APP_NAME, "Няма какво да се запише.")
            return
        stem = Path(self.audio_path.get()).stem if self.audio_path.get() else "output"
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"{stem}{suffix}",
            initialdir=self.out_dir.get() or str(Path.home()),
            filetypes=[("Текстов файл", "*.txt")],
        )
        if path:
            Path(path).write_text(content, encoding="utf-8")
            self.status.set(f"Записано: {path}")

    # ---------- worker ----------

    def _start(self):
        audio = self.audio_path.get().strip()
        if not audio or not Path(audio).exists():
            messagebox.showwarning(config.APP_NAME, "Първо избери валиден аудио файл.")
            return
        if self.worker and self.worker.is_alive():
            return

        self._save_settings()
        self.stop_event.clear()
        self.txt_transcript.delete("1.0", END)
        self.txt_summary.delete("1.0", END)
        self.bar["value"] = 0
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.combo.config(state="disabled")

        self.worker = threading.Thread(
            target=self._run,
            args=(audio, self.model_size.get(), self.out_dir.get().strip() or None, self.do_summary.get()),
            daemon=True,
        )
        self.worker.start()

    def _stop(self):
        self.stop_event.set()
        self.status.set("Спиране...")

    def _run(self, audio: str, size: str, out_dir, want_summary: bool):
        put = self.q.put
        summarizer = None
        try:
            if not models.is_whisper_ready(size):
                put(("status", "Първо стартиране: изтегляне на модели (еднократно)."))
                models.whisper_path(size, cb=lambda d, t, lbl: put(("dl", d, t, lbl)))
            if want_summary and not models.is_llm_ready():
                models.llm_path(cb=lambda d, t, lbl: put(("dl", d, t, lbl)))

            tr = transcribe.transcribe(
                audio,
                size=size,
                status=lambda m: put(("status", m)),
                progress=lambda p: put(("progress", p * (0.7 if want_summary else 1.0))),
                should_stop=self.stop_event.is_set,
            )
            put(("transcript", tr.text))
            paths = transcribe.save_outputs(audio, tr, out_dir)
            put(("status", f"Транскрипцията е записана: {paths['txt']}"))

            if want_summary:
                summarizer = summarize.Summarizer(status=lambda m: put(("status", m)))
                text = summarizer.summarize(
                    tr.text,
                    progress=lambda p: put(("progress", 0.7 + p * 0.3)),
                    should_stop=self.stop_event.is_set,
                )
                put(("summary", text))
                sp = summarize.save_summary(audio, text, out_dir)
                put(("status", f"Готово. Резюме: {sp}"))
            else:
                put(("status", "Готово."))

            put(("progress", 1.0))
            put(("done", None))
        except KeyboardInterrupt:
            put(("status", "Спряно."))
            put(("done", None))
        except Exception as exc:
            put(("error", f"{exc}\n\n{traceback.format_exc()}"))
        finally:
            if summarizer:
                summarizer.close()

    def _pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status.set(msg[1])
                elif kind == "progress":
                    self.bar["value"] = max(0, min(1000, int(msg[1] * 1000)))
                elif kind == "dl":
                    done, total, label = msg[1], msg[2], msg[3]
                    if total:
                        self.bar["value"] = int(done / total * 1000)
                        self.status.set(f"{label}: {done / 1e6:.0f} / {total / 1e6:.0f} MB")
                    else:
                        self.status.set(label)
                elif kind == "transcript":
                    self.txt_transcript.delete("1.0", END)
                    self.txt_transcript.insert("1.0", msg[1])
                elif kind == "summary":
                    self.txt_summary.delete("1.0", END)
                    self.txt_summary.insert("1.0", msg[1])
                elif kind == "error":
                    self._finish()
                    self.status.set("Грешка.")
                    messagebox.showerror(config.APP_NAME, msg[1][:2000])
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _finish(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.combo.config(state="readonly")

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel(config.APP_NAME, "Работи процес. Да затворя ли?"):
                return
            self.stop_event.set()
        self._save_settings()
        self.destroy()


def main():
    App().mainloop()
