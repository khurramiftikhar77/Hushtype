"""System tray icon that shows the current state."""

from __future__ import annotations

from typing import Callable

import pystray
from PIL import Image, ImageDraw

COLORS = {
    "loading": (128, 128, 128),
    "idle": (46, 160, 67),
    "recording": (218, 54, 51),
    "working": (219, 154, 4),
}
TITLES = {
    "loading": "LocalFlow: loading model...",
    "idle": "LocalFlow: hold Right Alt to dictate",
    "recording": "LocalFlow: listening",
    "working": "LocalFlow: transcribing",
}


def _icon(color) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=color)
    # simple microphone glyph
    d.rounded_rectangle((25, 15, 39, 38), radius=7, fill="white")
    d.arc((19, 24, 45, 44), start=0, end=180, fill="white", width=3)
    d.line((32, 44, 32, 50), fill="white", width=3)
    return img


class Tray:
    def __init__(self, on_quit: Callable[[], None]):
        self._images = {k: _icon(c) for k, c in COLORS.items()}
        self.icon = pystray.Icon(
            "LocalFlow",
            self._images["loading"],
            TITLES["loading"],
            menu=pystray.Menu(pystray.MenuItem("Quit", lambda: on_quit())),
        )

    def set_state(self, state: str) -> None:
        self.icon.icon = self._images[state]
        self.icon.title = TITLES[state]

    def run(self, setup: Callable[[pystray.Icon], None]) -> None:
        self.icon.run(setup=setup)

    def stop(self) -> None:
        self.icon.stop()
