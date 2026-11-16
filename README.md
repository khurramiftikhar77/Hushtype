# Hushtype

Offline push-to-talk dictation for Windows. Hold **Right Alt**, speak, release, and your words are typed into whatever app has focus: LinkedIn, Gmail, Word, Slack, Notepad.

Speech is transcribed on your own computer with [faster-whisper](https://github.com/SYSTRAN/faster-whisper). No audio or text leaves your machine.

## Features

- Works in any app that accepts text input
- Fully offline after the first model download
- Removes filler words ("um", "uh", "erm")
- Custom vocabulary and spelling fixes for names and terms
- Tray icon that shows what it is doing

## Privacy

Hushtype is built so that nothing you say leaves your computer.

- **Speech is processed on your laptop.** Audio goes from your microphone to the Whisper model running locally. It is never uploaded anywhere.
- **One download, then offline.** The first time a model is used, it is downloaded once from [Hugging Face](https://huggingface.co/Systran) (about 250 MB for English). After that Hushtype loads it from disk and makes no network connections at all. Usage statistics to Hugging Face are switched off. No audio or text is ever sent.
- **Audio is not saved.** Recordings live in memory only while you hold the key, then they are discarded. The one exception is `--mic-test`, which saves a test recording in the current folder so you can listen to it.
- **The keyboard listener only reacts to its own shortcut.** Hushtype has to listen to the keyboard to notice when you hold Right Alt. It does not record, store or send any other keys.
- **Your clipboard is restored.** Hushtype pastes through the clipboard, then puts back what you had copied before.
- **No accounts, no tracking, no analytics.** The code has no telemetry and no network calls. You can check: it is all in this repository.
- **Dependencies are pinned** to exact versions in `pyproject.toml`, so a future release of a third-party library cannot change what you install without an intentional update.

## Requirements

- Windows 10 or 11
- Python 3.12. With the Python install manager from [python.org](https://www.python.org/downloads/), run `py install 3.12`. Newer versions (3.15) are missing some required packages for now.
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
| `audio.mic` | Microphone to use; part of its name from `--list-devices`. Empty = Windows default |
| `hotkey.key` | Push-to-talk key, e.g. `alt_r`, `ctrl_r`, `f13` |
| `model.name` | `base.en` (fastest), `small.en` (default), `medium.en` (most accurate, slower) |
| `output.remove_fillers` | Strip "um", "uh" and similar |
| `output.trailing_space` | Add a space after each dictation |
| `output.beep` | Short beep when recording starts and stops |
| `vocabulary.words` | Names and terms Whisper should spell correctly |
| `[replacements]` | Fix words that keep coming out wrong, e.g. `"linked in" = "LinkedIn"` |

## Troubleshooting

- **Wrong or made-up text ("You", "Thank you", a random website).** Hushtype is not getting clean audio. Run `.\start.bat --mic-test`: it shows the recording level, saves `hushtype_mic_test.wav` so you can hear what it heard, and prints the text. If it is the wrong microphone, run `.\start.bat --list-devices` and set `mic` under `[audio]` in `config.toml`. Bluetooth headsets often give poor audio on Windows; the laptop mic is usually better.
- **Nothing happens when I hold Right Alt.** Run `.\start.bat -v` from a terminal and check the log. Make sure the tray icon is green.
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

## License

[MIT](LICENSE). Free to use, change and share.
