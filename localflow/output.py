"""Puts text into the focused app by pasting, then restores the clipboard."""

from __future__ import annotations

import sys
import threading
import time

import pyperclip
from pynput.keyboard import Controller, Key

_kb = Controller()


def paste_text(text: str) -> None:
    try:
        previous = pyperclip.paste()
    except Exception:
        previous = None

    pyperclip.copy(text)
    time.sleep(0.05)  # let the clipboard settle
    with _kb.pressed(Key.ctrl):
        _kb.press("v")
        _kb.release("v")

    if previous is not None:
        # Restore after the target app has read the clipboard.
        def restore():
            time.sleep(0.5)
            try:
                if pyperclip.paste() == text:
                    pyperclip.copy(previous)
            except Exception:
                pass

        threading.Thread(target=restore, daemon=True).start()


def beep(start: bool) -> None:
    if sys.platform != "win32":
        return
    import winsound

    freq = 880 if start else 660
    threading.Thread(target=winsound.Beep, args=(freq, 60), daemon=True).start()
