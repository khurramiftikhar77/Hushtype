# Hushtype

Offline push-to-talk dictation for Windows. Hold **Right Alt**, speak, release, and your words are typed into whatever app has focus: LinkedIn, Gmail, Word, Slack, Notepad.

Speech is transcribed on your own computer with [faster-whisper](https://github.com/SYSTRAN/faster-whisper). No audio or text leaves your machine.

## Features

- Works in any app that accepts text input
- Fully offline after the first model download
- Removes filler words ("um", "uh", "erm")
- Custom vocabulary and spelling fixes for names and terms
- Tray icon that shows what it is doing

## Requirements

- Windows 10 or 11
- Python 3.11 or newer from [python.org](https://www.python.org/downloads/) (tick **"Add python.exe to PATH"** during install)
- A microphone
- About 1 GB of free disk space and 8 GB of RAM or more

## Install and run

1. Download the code with **Code > Download ZIP**, or clone it:

   ```
   git clone https://github.com/khurramiftikhar77/Hushtype.git
   ```

2. Open the folder and double-click **`start.bat`**.

   The first launch creates a virtual environment, installs the dependencies and downloads the speech model (about 250 MB). This takes a few minutes. Later launches take a few seconds.

3. Wait until the tray icon turns green. It may be hidden under the `^` arrow on the taskbar.

## Usage

1. Click into a text field.
2. Hold **Right Alt** and speak.
3. Release. The text appears a moment later.

| Tray icon | Meaning |
|-----------|---------|
| Grey | Loading the model |
| Green | Ready |
| Red | Listening |
| Amber | Transcribing |

To quit, right-click the tray icon and choose **Quit**.

## Settings

Edit `config.toml` in the app folder, then restart Hushtype.

| Setting | What it does |
|---------|--------------|
| `hotkey.key` | Push-to-talk key, e.g. `alt_r`, `ctrl_r`, `f13` |
| `model.name` | `base.en` (fastest), `small.en` (default), `medium.en` (most accurate, slower) |
| `output.remove_fillers` | Strip "um", "uh" and similar |
| `output.trailing_space` | Add a space after each dictation |
| `output.beep` | Short beep when recording starts and stops |
| `vocabulary.words` | Names and terms Whisper should spell correctly |
| `[replacements]` | Fix words that keep coming out wrong, e.g. `"linked in" = "LinkedIn"` |

## Troubleshooting

- **Nothing happens when I hold Right Alt.** Run `start.bat -v` from a terminal and check the log. Make sure the tray icon is green.
- **No audio / empty text.** Check Windows Settings > Privacy & security > Microphone, and allow desktop apps to use the microphone.
- **Setup is blocked.** Windows Smart App Control can block Python. Check Windows Security > App & browser control.
- **Too slow.** Switch `model.name` to `base.en`.
- **Not accurate enough.** Switch `model.name` to `medium.en` and add frequently used names to `vocabulary.words`.

Test transcription without the microphone:

```
.venv\Scripts\python -m hushtype --file path\to\audio.wav
```

## Development

```
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m pytest
```

Project layout:

```
hushtype/
  app.py          wiring, worker thread, CLI
  audio.py        microphone capture with pre-roll buffer
  transcriber.py  faster-whisper wrapper
  cleanup.py      filler removal and text fixes
  hotkey.py       global push-to-talk listener
  output.py       paste into the focused app
  tray.py         system tray icon
config.toml       user settings
start.bat         one-click setup and launch
```
