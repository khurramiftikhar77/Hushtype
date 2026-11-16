"""Global dictation key.

- Hold the shortcut (e.g. Right Alt + Space): record. Release: transcribe and paste.
- Double-tap it (tap Space twice while holding Right Alt): hands-free. Tap again to stop.
- Modifier + L: switch the active project between English and Urdu.
- Modifier + V: paste the last dictation again.

On Windows the shortcut keys (and L / V with the modifier) are swallowed, so
other apps never see them. That stops Alt from opening menus and keeps the
shortcuts from typing into the document. Space on its own types normally.
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

# Shortcut name -> (modifier key, main key). Without a modifier the single key is held.
VK_SPACE, VK_L, VK_V = 0x20, 0x4C, 0x56
VK_RALT, VK_RCTRL = 0xA5, 0xA3
SHORTCUTS = {
    "alt_r+space": (VK_RALT, VK_SPACE),
    "ctrl_r+space": (VK_RCTRL, VK_SPACE),
    "alt_r": (None, VK_RALT),
    "ctrl_r": (None, VK_RCTRL),
    "shift_r": (None, 0xA1),
    "caps_lock": (None, 0x14),
    "f8": (None, 0x77),
    "f9": (None, 0x78),
    "f10": (None, 0x79),
}
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


class KeyRouter:
    """Turns raw key events into HotkeyLogic calls and decides what to swallow.

    Pure logic (no OS calls) so it can be tested with plain virtual-key codes.
    """

    def __init__(self, shortcut: str, logic: HotkeyLogic):
        if shortcut not in SHORTCUTS:
            raise ValueError(f"Unknown shortcut '{shortcut}'")
        self.mod_vk, self.key_vk = SHORTCUTS[shortcut]
        self.logic = logic
        self.mod_down = False
        self.key_down = False  # main key currently held as part of the shortcut
        self._swallowed: set[int] = set()  # keys whose down we swallowed, so we swallow their up
        self._pending_repaste = False

    def event(self, vk: int, down: bool) -> bool:
        """Returns True if the event must be hidden from other apps."""
        if self.mod_vk is None:
            return self._single(vk, down)
        return self._combo(vk, down)

    def _single(self, vk: int, down: bool) -> bool:
        if vk == self.key_vk:
            self.logic.key_down() if down else self.logic.key_up()
            return True
        return self._letters(vk, down, self.logic.held)

    def _combo(self, vk: int, down: bool) -> bool:
        if vk == self.mod_vk:
            if down:
                self.mod_down = True
            else:
                self.mod_down = False
                if self.key_down:  # released the modifier first
                    self.key_down = False
                    self.logic.key_up()
                if self._pending_repaste:
                    self._pending_repaste = False
                    self.logic._do("repaste")
            return True  # the modifier never reaches apps (no Alt menus)
        if vk == self.key_vk:
            if down and (self.mod_down or self.key_down):
                if not self.key_down:
                    self.key_down = True
                    self._swallowed.add(vk)
                    self.logic.key_down()
                return True
            if not down and vk in self._swallowed:
                self._swallowed.discard(vk)
                if self.key_down:
                    self.key_down = False
                    self.logic.key_up()
                return True
            return False  # plain Space types normally
        return self._letters(vk, down, self.mod_down)

    def _letters(self, vk: int, down: bool, modifier_held: bool) -> bool:
        if vk not in (VK_L, VK_V) or not self.logic.combos_enabled:
            return False
        if down and modifier_held:
            which = "l" if vk == VK_L else "v"
            if self.logic.held:
                self.logic.combo(which)
            elif which == "l":
                self.logic._do("toggle_language")
            else:
                self._pending_repaste = True  # paste once the modifier is released
            self._swallowed.add(vk)
            return True
        if not down and vk in self._swallowed:
            self._swallowed.discard(vk)
            return True
        return False


class Hotkeys:
    """Connects KeyRouter to the real keyboard. Actions run off the hook thread."""

    def __init__(self, shortcut: str, actions: dict[str, Callable[[], None]],
                 hands_free: bool = True, combos: bool = True):
        self._queue: queue.Queue = queue.Queue()
        safe = {name: (lambda f=fn: self._queue.put(f)) for name, fn in actions.items()}
        self.logic = HotkeyLogic(safe, hands_free=hands_free, combos=combos)
        self.router = KeyRouter(shortcut, self.logic)
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
        else:  # development on other systems: no swallowing
            def vk_of(k):
                return getattr(k, "vk", None) or getattr(getattr(k, "value", None), "vk", None)

            self._listener = keyboard.Listener(
                on_press=lambda k: self.router.event(vk_of(k), True),
                on_release=lambda k: self.router.event(vk_of(k), False))
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
        self._queue.put(None)

    def _win32_filter(self, msg, data) -> bool:
        # Runs inside the Windows keyboard hook: keep it fast, never block.
        if data.flags & _INJECTED:
            return True  # our own simulated Ctrl+V and similar
        if msg in _DOWN or msg in _UP:
            if self.router.event(data.vkCode, msg in _DOWN):
                self._listener.suppress_event()
        return True
