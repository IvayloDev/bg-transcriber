# BG Transcriber

Offline Windows desktop app: drop in a Bulgarian audio file, get a full transcript and a structured summary. No API keys, no cloud, no per-minute cost.

- Transcription: `faster-whisper` (CTranslate2), int8 on CPU
- Summary: Gemma 3 4B via `llama.cpp`, map-reduce over the transcript
- Outputs: `<name>_transcript.txt`, `<name>_transcript.srt`, `<name>_summary.txt`

## Why models download on first run

GitHub caps release assets at 2 GB, so the installer ships code only (~250 MB). On first launch the app downloads Whisper (~1.5 GB for `medium`) and the summary model (~2.5 GB) into `%LOCALAPPDATA%\BGTranscriber\models`. That needs internet once. Everything after that is fully offline.

## Speed expectations (laptop, no GPU)

| Step | 1 hour of audio |
| --- | --- |
| Transcribe (`medium`, int8) | 25 to 40 min |
| Summarize (Gemma 3 4B Q4) | 2 to 5 min |

`small` is roughly 3x faster with noticeably rougher Bulgarian. `large-v3` is the most accurate and far too slow on CPU for long files. Needs about 4 GB of free RAM.

## Build

Windows binaries are built by GitHub Actions, since PyInstaller cannot cross-compile from macOS or Linux.

```bash
git push origin main
git tag v1.0.0 && git push origin v1.0.0
```

The tag triggers `.github/workflows/build.yml`, which produces `BG-Transcriber-Setup.exe` and `BG-Transcriber-portable.zip` and attaches them to the release. `workflow_dispatch` runs the same build without publishing a release.

## Run from source

```bash
pip install -r requirements.txt
python run.py
```

## Layout

| Path | Role |
| --- | --- |
| `app/config.py` | Paths, model catalogue, chunk sizes |
| `app/models.py` | First run downloads with byte level progress |
| `app/transcribe.py` | faster-whisper wrapper, txt and srt output |
| `app/summarize.py` | llama.cpp map-reduce summariser, Bulgarian prompts |
| `app/gui.py` | Tkinter UI, worker thread, progress queue |
| `build/app.spec` | PyInstaller one-dir spec |
| `build/installer.iss` | Inno Setup, per-user install, no admin rights |

---

## За потребителя

1. Изтегли `BG-Transcriber-Setup.exe` от страницата с изданията и го инсталирай. Не са нужни администраторски права.
2. Пусни приложението. При първото стартиране сваля моделите веднъж, около 4 GB. Остави го да завърши.
3. Натисни "Избери...", посочи аудио файла, натисни "Старт".
4. Готовите файлове се записват до аудиото: транскрипция (`.txt` и `.srt`) и резюме (`.txt`).

След първото сваляне приложението работи без интернет.
