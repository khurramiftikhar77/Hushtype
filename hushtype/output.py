"""Puts text into the focused app by pasting, then restores the clipboard."""

from __future__ import annotations

import sys
import threading
import time

import pyperclip
from pynput.keyboard import Controller, Key

_kb = Controller()


def copy_text(text: str) -> None:
    pyperclip.copy(text)


def paste_text(text: str, keep_on_clipboard: bool = True) -> None:
    """Pastes text into the focused app with Ctrl+V.

    keep_on_clipboard=True leaves the text on the clipboard afterwards, so it
    can be pasted again by hand. False restores what was copied before.
    """
    previous = None
    if not keep_on_clipboard:
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
