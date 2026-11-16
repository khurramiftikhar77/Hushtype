"""Global dictation key.

- Hold the key: record. Release: transcribe and paste.
- Double-tap the key: hands-free recording. Tap again to stop.
- Key + L: switch the active project between English and Urdu.
- Key + V: paste the last dictation again.

On Windows the dictation key (and L / V while it is held) is swallowed, so
other apps never see it. That stops Alt from opening menus and keeps the
shortcuts from typing into the document.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

TAP_MAX = 0.30  # a press shorter than this is a tap
DOUBLE_TAP_GAP = 0.45  # max time between two taps

VK = {"alt_r": 0xA5, "ctrl_r": 0xA3, "shift_r": 0xA1, "caps_lock": 0x14,
      "f8": 0x77, "f9": 0x78, "f10": 0x79}
VK_L, VK_V = 0x4C, 0x56
_DOWN = (0x100, 0x104)  # WM_KEYDOWN, WM_SYSKEYDOWN
_UP = (0x101, 0x105)
_INJECTED = 0x10


class HotkeyLogic:
    """Turns key events into actions. Pure logic, no OS calls, so it is testable.

    Callbacks: start, stop, cancel, toggle_language, repaste.
    """

    def __init__(self, actions: dict[str, Callable[[], None]], hands_free: bool = True,
                 combos: bool = True, clock: Callable[[], float] = time.monotonic):
        self.actions = actions
        self.hands_free_enabled = hands_free
        self.combos_enabled = combos
        self.clock = clock
        self.held = False
        self.hands_free = False
        self._down_at = 0.0
        self._last_tap_end = -10.0
        self._combo_used = False
        self._swallow_release = False
        self._pending_repaste = False

    def _do(self, name: str) -> None:
        fn = self.actions.get(name)
        if fn:
            fn()

    def key_down(self) -> None:
        if self.held:  # auto-repeat while held
            return
        self.held = True
        if self.hands_free:
            # A press while hands-free stops the recording.
            self.hands_free = False
            self._swallow_release = True
            self._do("stop")
            return
        self._down_at = self.clock()
        self._combo_used = False
        self._do("start")

    def key_up(self) -> None:
        if not self.held:
            return
        self.held = False
        now = self.clock()
        if self._swallow_release:
            self._swallow_release = False
            return
        if self._combo_used:
            if self._pending_repaste:
                self._pending_repaste = False
                self._do("repaste")
            return
        if now - self._down_at < TAP_MAX:
            if self.hands_free_enabled and now - self._last_tap_end < DOUBLE_TAP_GAP:
                self.hands_free = True  # keep recording, started on this press
                self._last_tap_end = -10.0
                self._do("hands_free")
                return
            self._last_tap_end = now
            self._do("cancel")  # a single short tap is not a dictation
            return
        self._do("stop")

    def combo(self, which: str) -> bool:
        """L or V pressed while the key is held. Returns True if handled."""
        if not (self.held and self.combos_enabled):
            return False
        if not self._combo_used:
            self._combo_used = True
            self._do("cancel")
        if which == "l":
            self._do("toggle_language")
        elif which == "v":
            self._pending_repaste = True
        return True


class Hotkeys:
    """Connects HotkeyLogic to the real keyboard. Actions run off the hook thread."""

    def __init__(self, key_name: str, actions: dict[str, Callable[[], None]],
                 hands_free: bool = True, combos: bool = True):
        if key_name not in VK:
            raise ValueError(f"Unknown key '{key_name}'")
        self.key_name = key_name
        self.vk = VK[key_name]
        self._queue: queue.Queue = queue.Queue()
        safe = {name: (lambda f=fn: self._queue.put(f)) for name, fn in actions.items()}
        self.logic = HotkeyLogic(safe, hands_free=hands_free, combos=combos)
        self._combo_keys_down: set[int] = set()
        self._listener = None
        threading.Thread(target=self._dispatch, daemon=True).start()

    def _dispatch(self) -> None:
        while True:
            fn = self._queue.get()
            if fn is None:
                return
            try:
                fn()
            except Exception:
                log.exception("Hotkey action failed")

    def start(self) -> None:
        from pynput import keyboard

        if sys.platform == "win32":
            self._listener = keyboard.Listener(win32_event_filter=self._win32_filter)
        else:
            key = getattr(keyboard.Key, self.key_name)

            def on_press(k):
                if k == key:
                    self.logic.key_down()
                elif getattr(k, "char", None) in ("l", "v"):
                    self.logic.combo(k.char)

            def on_release(k):
                if k == key:
                    self.logic.key_up()

            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
        self._queue.put(None)

    def _win32_filter(self, msg, data) -> bool:
        # Runs inside the Windows keyboard hook: keep it fast, never block.
        if data.flags & _INJECTED:
            return True  # our own simulated Ctrl+V and similar
        vk = data.vkCode
        if vk == self.vk:
            if msg in _DOWN:
                self.logic.key_down()
            elif msg in _UP:
                self.logic.key_up()
            self._listener.suppress_event()
        if vk in (VK_L, VK_V):
            if msg in _DOWN and self.logic.combo("l" if vk == VK_L else "v"):
                self._combo_keys_down.add(vk)
                self._listener.suppress_event()
            elif msg in _UP and vk in self._combo_keys_down:
                self._combo_keys_down.discard(vk)
                self._listener.suppress_event()
        return True
