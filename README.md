# Hushtype

Offline voice dictation for Windows. Hold **Right Alt**, speak, release, and your words are typed wherever your cursor is: LinkedIn, Gmail, Outlook, Word, WhatsApp, anywhere.

Speech is transcribed on your own computer with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), an open-source version of OpenAI's Whisper. No audio or text leaves your machine.

## Features

- **Dictate anywhere:** works in any app that accepts text
- **English and Urdu:** switch per project, or with Right Alt + L
- **Automatic punctuation:** commas, full stops and question marks are added for you. Say "new line" or "new paragraph" for line breaks.
- **Projects:** group dictations (Email, Work, Poetry...). Each project has its own language and text style, and can auto-file by app (Outlook goes to Email).
- **History:** search, filter, copy, move between projects. A Combined view joins a project into one document.
- **Snippets:** say "my signature" and get your full signature
- **Hands-free:** double-tap Right Alt to keep recording without holding the key
- **Paste again:** Right Alt + V re-pastes your last dictation
- **Recording pill:** a small timer and sound wave at the bottom of the screen while you talk
- **Filler removal:** "um", "uh", "erm" are dropped
- **Runs in the tray** and can start with Windows
- **Fully offline** after a one-time model download

## Install

### Option 1: installer (recommended)

1. Go to [Releases](https://github.com/khurramiftikhar77/Hushtype/releases) and download `Hushtype-Setup-x.y.z.exe`.
2. Run it. No admin rights are needed. Windows may show "Windows protected your PC" because the installer is not code-signed yet: click **More info**, then **Run anyway**.
3. Hushtype opens. The first start downloads the English speech model (about 490 MB), which takes a few minutes once.

Builds of the latest code are also available under the repository's **Actions** tab: open the newest successful "Build Windows installer" run and download the file under **Artifacts**.

### Option 2: run from source (for developers)

Needs Python 3.12 (with the Python install manager from python.org: `py install 3.12`).

```
git clone https://github.com/khurramiftikhar77/Hushtype.git
cd Hushtype
start.bat
```

The first run creates a virtual environment and installs everything.

## How to use

| Do this | What happens |
|---|---|
| Hold **Right Alt**, speak, release | Your words are pasted where the cursor is |
| Double-tap **Right Alt** | Hands-free recording. Tap again to finish |
| **Right Alt + L** | Switch the active project between English and Urdu |
| **Right Alt + V** | Paste your last dictation again |
| Say "new line" / "new paragraph" | Line breaks. Punctuation is automatic |
| Say a snippet trigger, e.g. "my signature" | Inserts the saved text |

The main window (open it from the tray icon) has four screens:

- **Home:** status, language toggle, active project, your last dictation and a reminder of all shortcuts
- **History:** everything you dictated, with time, recording length and the app it went into
- **Projects:** create projects, set their language, style and app rules, and see a project as one combined document
- **Settings:** microphone with a live level meter and test, shortcut key, models, snippets, your words, start with Windows, history

Closing the window keeps Hushtype running in the tray. To quit, right-click the tray icon.

## Urdu

Urdu uses a larger multilingual model (`large-v3-turbo`, about 1.6 GB) that downloads the first time you switch a project to Urdu. On a laptop CPU, expect a few seconds more per sentence than English. Text is written in Urdu script. Mixing English and Urdu in one sentence is not supported well by Whisper yet: pick one language per dictation.

## Privacy

Hushtype is built so that nothing you say leaves your computer.

- **Speech is processed on your laptop.** Audio goes from your microphone to the Whisper model running locally. It is never uploaded anywhere.
- **One download per model, then offline.** The first time a model is used, it is downloaded once from [Hugging Face](https://huggingface.co/Systran). After that Hushtype loads it from disk and makes no network connections at all. Usage statistics to Hugging Face are switched off. No audio or text is ever sent.
- **Audio is not saved.** Recordings live in memory only while you speak, then they are discarded. The one exception is the `--mic-test` command, which saves a test recording in the current folder so you can listen to it.
- **History stays local.** Dictations are stored in `%APPDATA%\Hushtype` on your computer. You can turn history off, delete items, and Hushtype asks every week whether to clean up old entries.
- **The keyboard listener only reacts to its own shortcuts.** Hushtype listens to the keyboard to notice Right Alt (and L or V while it is held). It does not record, store or send any other keys.
- **Your clipboard is restored.** Hushtype pastes through the clipboard, then puts back what you had copied before.
- **No accounts, no tracking, no analytics.** The code has no telemetry. You can check: it is all in this repository.
- **Dependencies are pinned** to exact versions in `pyproject.toml`, so a future release of a third-party library cannot change what you install without an intentional update.

## Requirements

- Windows 10 or 11, 64-bit. Windows 10 needs the Microsoft Edge WebView2 Runtime, which most PCs already have.
- A microphone
- 8 GB of RAM or more; about 1 GB of disk space for English, 3 GB with Urdu

## Troubleshooting

- **Made-up text like "You" or "Thank you".** Hushtype is not getting clean audio. In Settings, pick your microphone and press **Test microphone**: speak and check that the level bar moves to about the middle. Bluetooth headsets often give poor audio on Windows; the laptop microphone is usually better.
- **Nothing happens when I hold Right Alt.** Check the tray icon: grey means it is still loading the model. If you use a keyboard layout where Right Alt is AltGr, pick another key in Settings.
- **Text goes to the wrong place.** Press Right Alt + V in the right box to paste it again.
- **Too slow.** In Settings, choose the Fast model.
- **Not accurate enough.** Choose the Accurate model, and add names and terms under My words.
- **Logs:** `%APPDATA%\Hushtype\hushtype.log`

Command-line options (from source, or `Hushtype.exe` in its install folder):

```
--mic-test          record 5 seconds, show the level, save a WAV, transcribe it
--list-devices      list microphones
--file audio.wav    transcribe a file
--language ur       use Urdu for --file / --mic-test
--background        start in the tray without opening the window
-v                  verbose logging
```

## Development

```
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m pytest
```

| Path | What it does |
|---|---|
| `hushtype/engine.py` | Hotkey to microphone to Whisper to cleanup to paste to history |
| `hushtype/hotkey.py` | Hold, double-tap, Right Alt + L / V |
| `hushtype/transcriber.py` | faster-whisper wrapper, offline model loading |
| `hushtype/cleanup.py` | Fillers, line breaks, snippets, capitalisation |
| `hushtype/store.py` | SQLite: projects, app rules, history |
| `hushtype/gui.py`, `hushtype/ui/` | Desktop windows (pywebview + WebView2) and their HTML |
| `hushtype/tray.py` | Tray icon and menu |
| `packaging/` | PyInstaller spec, Inno Setup installer, icon |
| `.github/workflows/build.yml` | Builds, tests and self-tests the installer on every push; tags publish a release |

To publish a release: bump `__version__` in `hushtype/__init__.py` and `version` in `pyproject.toml`, then push a tag like `v0.2.0`.

## License

[MIT](LICENSE). Free to use, change and share.
