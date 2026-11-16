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

LANGUAGES = {"en": "English", "ur": "Urdu"}

MODELS = {
    "en": {
        "base.en": "Fast (lower accuracy)",
        "small.en": "Balanced (recommended)",
        "medium.en": "Accurate (slower)",
    },
    "ur": {
        "small": "Fast (weak Urdu)",
        "medium": "Balanced",
        "large-v3-turbo": "Best Urdu (recommended, slower)",
    },
}
MODEL_SIZES = {
    "base.en": "150 MB", "small.en": "490 MB", "medium.en": "1.5 GB",
    "small": "490 MB", "medium": "1.5 GB", "large-v3-turbo": "1.6 GB",
}

HOTKEYS = {
    "alt_r": "Right Alt",
    "ctrl_r": "Right Ctrl",
    "shift_r": "Right Shift",
    "caps_lock": "Caps Lock",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
}

REVIEW_INTERVALS = {7: "Every week", 30: "Every month", 0: "Never"}

DEFAULTS: dict = {
    "hotkey": "alt_r",
    "language_switch_key": True,  # hotkey + L flips the active project's language
    "mic": "",  # device name; empty = Windows default
    "en_model": "small.en",
    "ur_model": "large-v3-turbo",
    "beam_size": 5,
    "cpu_threads": 0,
    "min_duration": 0.4,
    "preroll": 0.3,
    "trailing_space": True,
    "beep": False,
    "show_pill": True,
    "start_with_windows": True,
    "save_history": True,
    "review_days": 7,
    "last_review": None,  # ISO timestamp of the last cleanup prompt
    "active_project": 1,
    "vocabulary": ["LinkedIn"],
    "replacements": {"linked in": "LinkedIn"},
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
            except Exception:
                log.exception("Could not read settings, using defaults")
        if not self._data["last_review"]:
            # The first cleanup prompt comes one review period after first run.
            self._data["last_review"] = now_iso()
        self.save()

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
