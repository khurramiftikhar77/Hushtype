"""Global push-to-talk key listener.

Holding Alt and releasing it with no other key in between makes many Windows
apps (Notepad, Office, browsers) jump to their menu bar, which would swallow the
paste. To prevent that we tap an unassigned virtual key (0xE8) while Alt is
down, the same "menu mask" trick AutoHotkey uses.
"""

from __future__ import annotations

import sys
from typing import Callable

from pynput import keyboard

_MASK_VK = 0xE8


def _resolve(name: str):
    name = name.lower().strip()
    if hasattr(keyboard.Key, name):
        return getattr(keyboard.Key, name)
    raise ValueError(f"Unknown hotkey '{name}'. Use names like alt_r, ctrl_r, f13.")


def _send_mask_key() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(_MASK_VK, 0, 0, 0)
    user32.keybd_event(_MASK_VK, 0, KEYEVENTF_KEYUP, 0)


class PushToTalk:
    def __init__(self, key_name: str, on_down: Callable[[], None], on_up: Callable[[], None]):
        self.key = _resolve(key_name)
        # On some layouts Right Alt is reported as AltGr.
        self.keys = {self.key}
        if self.key == keyboard.Key.alt_r:
            self.keys.add(keyboard.Key.alt_gr)
        self.is_alt = self.key in (keyboard.Key.alt_r, keyboard.Key.alt_l, keyboard.Key.alt)
        self.on_down = on_down
        self.on_up = on_up
        self._held = False
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()

    def _press(self, key) -> None:
        if key in self.keys and not self._held:  # ignore auto-repeat
            self._held = True
            if self.is_alt:
                _send_mask_key()
            self.on_down()

    def _release(self, key) -> None:
        if key in self.keys and self._held:
            self._held = False
            self.on_up()
