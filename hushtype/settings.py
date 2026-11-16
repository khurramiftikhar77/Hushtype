"""Global user settings, stored as JSON in the Hushtype data folder.

Per-project options (language, filler removal, capitalisation) live in the
database with the project, see store.py.
"""

from __future__ import annotations

import copy
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from hushtype.paths import settings_path

log = logging.getLogger(__name__)

LANGUAGES = {"auto": "Auto", "en": "English", "ur": "Urdu", "pa": "Punjabi", "hi": "Hindi",
             "ar": "Arabic", "fa": "Persian", "ps": "Pashto", "sd": "Sindhi"}
NATIVE_NAMES = {"ur": "اردو", "pa": "پنجابی", "hi": "हिन्दी", "ar": "العربية", "fa": "فارسی",
                "ps": "پښتو", "sd": "سنڌي"}
RTL_LANGUAGES = ["ur", "pa", "ar", "fa", "ps", "sd"]
# Which downloaded model each language uses. Punjabi (Pakistani, written in
# Urdu script / Shahmukhi) shares the Urdu model, steered by a Punjabi prompt.
MODEL_LANGUAGE = {"pa": "ur"}  # Punjabi shares the Urdu model setting; others have their own
# Auto: a small multilingual model listens first and decides which model writes the text.
# Whisper often labels Urdu speech as Hindi (they sound the same), so both count as Urdu.
SOUTH_ASIAN = ("ur", "hi", "pa")
EXPERIMENTAL_LANGUAGES = ["pa", "ps", "sd"]

ENGLISH_MODELS = {
    "base.en": "Fast (lower accuracy)",
    "small.en": "Balanced (recommended)",
    "medium.en": "Accurate (slower)",
}
MULTILINGUAL_MODELS = {
    "small": "Fast (weaker)",
    "medium": "Balanced",
    "large-v3-turbo": "Best (recommended, slower)",
}
MODELS = {"en": ENGLISH_MODELS, "ur": MULTILINGUAL_MODELS}


def model_options(language: str) -> dict:
    return ENGLISH_MODELS if language == "en" else MULTILINGUAL_MODELS
MODEL_SIZES = {
    "base.en": "150 MB", "small.en": "490 MB", "medium.en": "1.5 GB",
    "small": "490 MB", "medium": "1.5 GB", "large-v3-turbo": "1.6 GB",
}
# Approximate download sizes in bytes, for the progress bar.
MODEL_BYTES = {
    "tiny.en": 75_000_000, "base": 145_000_000, "base.en": 145_000_000, "small.en": 484_000_000, "medium.en": 1_530_000_000,
    "small": 484_000_000, "medium": 1_530_000_000, "large-v3-turbo": 1_620_000_000,
}
SETTINGS_VERSION = 3

HOTKEYS = {
    "alt_r+space": "Right Alt + Space",
    "ctrl_r+space": "Right Ctrl + Space",
    "alt_r": "Right Alt",
    "ctrl_r": "Right Ctrl",
    "shift_r": "Right Shift",
    "caps_lock": "Caps Lock",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
}

REVIEW_INTERVALS = {7: "Every week", 30: "Every month", 0: "Never"}
MAX_RECORDING = {60: "1 minute", 120: "2 minutes (recommended)", 180: "3 minutes", 300: "5 minutes"}

DEFAULTS: dict = {
    "settings_version": SETTINGS_VERSION,
    "hotkey": "alt_r+space",
    "language_switch_key": True,  # hotkey + L flips the active project's language
    "mic": "",  # device name; empty = Windows default
    "en_model": "small.en",
    "ur_model": "large-v3-turbo",
    "detect_model": "base",  # language detector for Auto
    "auto_other": "ur",  # Auto: Urdu-sounding speech is written as Urdu ("ur") or Punjabi ("pa")
    "languages_enabled": ["en", "ur", "pa"],  # shown in the language switch
    "models": {},  # model for languages other than English/Urdu, e.g. {"ar": "large-v3-turbo"}
    "beam_size": 5,
    "cpu_threads": 0,
    "min_duration": 0.4,
    "max_seconds": 120,  # recording stops by itself after this, with a countdown
    "preroll": 0.3,
    "trailing_space": True,
    "auto_paste": False,  # off: only copy, you paste with Ctrl+V. On: also paste into the app
    "keep_on_clipboard": True,  # leave the dictation on the clipboard for Ctrl+V
    "beep": False,
    "theme": "system",  # system | light | dark
    "show_pill": True,
    "start_with_windows": True,
    "save_history": True,
    "review_days": 7,
    "last_review": None,  # ISO timestamp of the last cleanup prompt
    "active_project": 1,
    "hands_free": True,  # double-tap the key to keep recording without holding it
    "spoken_commands": True,  # "new line", "new paragraph", "full stop" ...
    "vocabulary": ["LinkedIn"],
    "replacements": {"linked in": "LinkedIn"},
    # Say the trigger, get the text. Edited on the Settings screen.
    "snippets": {"my signature": "Best regards,\nKhurram"},
    "self_correction": True,  # "Monday, no wait, Tuesday" -> "Tuesday"
    "smart_lists": True,  # "First... Second..." -> numbered list
    "email_layout": True,  # greeting and sign-off on their own lines in email apps
    "boost_quiet": True,  # whisper mode: raise the volume of quiet speech
    "learn_from_edits": True,  # fixes made in History are applied to future dictations
    "learn_names": True,  # names used in 3 dictations are added to the words Whisper should know
    "learned_replacements": {},  # {"sara": "Sarah"}
    "learned_words": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Settings:
    """Thread-safe settings with defaults filled in. Saved on every change."""

    def __init__(self, path: Path | None = None):
        self.path = path or settings_path()
        self._lock = threading.Lock()
        self._data = copy.deepcopy(DEFAULTS)
        self.first_run = not self.path.exists()
        if not self.first_run:
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                self._data.update({k: v for k, v in stored.items() if k in DEFAULTS})
                self._migrate(stored)
            except Exception:
                log.exception("Could not read settings, using defaults")
        if not self._data["last_review"]:
            # The first cleanup prompt comes one review period after first run.
            self._data["last_review"] = now_iso()
        self.save()

    def _migrate(self, stored: dict) -> None:
        version = stored.get("settings_version", 1)
        if version < 2 and stored.get("hotkey", "alt_r") == "alt_r":
            # v2: the default shortcut became Right Alt + Space.
            self._data["hotkey"] = "alt_r+space"
        if version < 3:
            # v3: dictations are only copied by default; you paste with Ctrl+V.
            self._data["auto_paste"] = False
            self._data["keep_on_clipboard"] = True
        self._data["settings_version"] = SETTINGS_VERSION

    def __getitem__(self, key: str):
        with self._lock:
            return copy.deepcopy(self._data[key])

    def all(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def update(self, changes: dict) -> dict:
        """Applies known keys and returns the ones whose value changed."""
        changed = {}
        with self._lock:
            for k, v in changes.items():
                if k in DEFAULTS and self._data.get(k) != v:
                    self._data[k] = v
                    changed[k] = v
        if changed:
            self.save()
        return changed

    def save(self) -> None:
        with self._lock:
            text = json.dumps(self._data, indent=2, ensure_ascii=False)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.path)
