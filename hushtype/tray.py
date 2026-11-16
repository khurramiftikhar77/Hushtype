"""System tray icon with a quick menu: open, project, language, quit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from hushtype.gui import Gui

COLORS = {
    "loading": (148, 156, 170),
    "model": (148, 156, 170),
    "idle": (20, 184, 166),
    "recording": (239, 68, 68),
    "working": (129, 140, 248),
    "error": (245, 158, 11),
}
TITLES = {
    "loading": "Hushtype: starting",
    "model": "Hushtype: loading model",
    "idle": "Hushtype: hold Right Alt to dictate",
    "recording": "Hushtype: listening",
    "working": "Hushtype: transcribing",
    "error": "Hushtype: needs attention",
}


def icon_image(color=(20, 184, 166), size: int = 64) -> Image.Image:
    """The Hushtype mark: a microphone on a rounded square."""
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=16 * s, fill=color)
    d.rounded_rectangle((25 * s, 12 * s, 39 * s, 37 * s), radius=7 * s, fill="white")
    d.arc((17 * s, 22 * s, 47 * s, 46 * s), start=0, end=180, fill="white", width=max(1, int(4 * s)))
    d.line((32 * s, 46 * s, 32 * s, 53 * s), fill="white", width=max(1, int(4 * s)))
    return img


class Tray:
    def __init__(self, gui: "Gui"):
        import pystray

        self.gui = gui
        self._pystray = pystray
        self._images = {k: icon_image(c) for k, c in COLORS.items()}
        self.icon = pystray.Icon("Hushtype", self._images["loading"], TITLES["loading"], menu=self._menu())

    def _menu(self):
        ps = self._pystray
        gui = self.gui

        def project_items():
            active = gui.settings["active_project"]
            for p in gui.store.projects():
                yield ps.MenuItem(
                    p["name"], lambda _i, _it, pid=p["id"]: gui.api.set_active_project(pid),
                    checked=lambda _it, pid=p["id"]: gui.settings["active_project"] == pid, radio=True)

        def lang_checked(lang):
            return lambda _it: gui.engine.live()["project"].get("language") == lang

        return ps.Menu(
            ps.MenuItem("Open Hushtype", lambda: gui.show_main(), default=True),
            ps.Menu.SEPARATOR,
            ps.MenuItem("Project", ps.Menu(project_items)),
            ps.MenuItem("English", lambda: gui.api.set_language("en"), checked=lang_checked("en"), radio=True),
            ps.MenuItem("Urdu", lambda: gui.api.set_language("ur"), checked=lang_checked("ur"), radio=True),
            ps.Menu.SEPARATOR,
            ps.MenuItem("Quit Hushtype", lambda: gui.quit()),
        )

    def set_state(self, state: str) -> None:
        if state in self._images:
            self.icon.icon = self._images[state]
            self.icon.title = TITLES[state]

    def refresh(self) -> None:
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def run(self) -> None:
        self.icon.run()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass
