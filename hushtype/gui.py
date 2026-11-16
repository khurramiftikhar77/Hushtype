"""Desktop windows (pywebview + Edge WebView2): the main app and the floating pill.

The HTML in hushtype/ui talks to Python only through the Api class below.
"""

from __future__ import annotations

import logging
import threading
import time

from hushtype import BUILD, __version__, winutil
from hushtype.engine import Engine
from hushtype.paths import data_dir, resource_path
from hushtype.settings import (HOTKEYS, LANGUAGES, MODEL_SIZES, MODELS, REVIEW_INTERVALS, Settings)
from hushtype.store import Store

log = logging.getLogger(__name__)

PILL_W, PILL_H = 380, 76


class Api:
    """Methods callable from JavaScript as `pywebview.api.<name>(...)`.

    Attributes start with an underscore so pywebview does not expose them.
    """

    def __init__(self, gui: "Gui"):
        self._gui = gui

    @property
    def _e(self) -> Engine:
        return self._gui.engine

    @property
    def _s(self) -> Settings:
        return self._gui.settings

    @property
    def _db(self) -> Store:
        return self._gui.store

    # ----- reading -----

    def bootstrap(self) -> dict:
        return {
            "version": __version__,
            "build": BUILD,
            "settings": self._s.all(),
            "options": {
                "languages": LANGUAGES,
                "models": MODELS,
                "model_sizes": MODEL_SIZES,
                "hotkeys": HOTKEYS,
                "review_intervals": {str(k): v for k, v in REVIEW_INTERVALS.items()},
            },
            "projects": self._db.projects(),
            "stats": self._db.stats(),
            "last": self._db.last(),
            "models": self.models(),
            "data_dir": str(data_dir()),
        }

    def live(self) -> dict:
        return self._e.live()

    def stats(self) -> dict:
        return {"stats": self._db.stats(), "last": self._db.last(), "projects": self._db.projects(),
                "settings": self._s.all()}

    def models(self) -> dict:
        out = {}
        for lang in LANGUAGES:
            out[lang] = {
                "name": self._e.model_name(lang),
                "on_disk": self._e.model_ready_on_disk(lang),
                "loading": lang in self._e.loading_models,
                "error": self._e.model_errors.get(lang),
            }
        return out

    def mics(self) -> list[dict]:
        try:
            import sounddevice as sd

            from hushtype.audio import list_input_devices

            default = sd.default.device[0]
            seen, out = set(), []
            for idx, name, api in list_input_devices():
                if api != "MME" or name in seen:  # one entry per device
                    continue
                seen.add(name)
                out.append({"name": name, "default": idx == default})
            return out
        except Exception:
            log.exception("Listing microphones failed")
            return []

    def mic_level(self) -> float:
        r = self._e.recorder
        return r.level if r else 0.0

    def history(self, params: dict | None = None) -> list[dict]:
        p = params or {}
        return self._db.dictations(query=p.get("query", ""), project_id=p.get("project_id") or None,
                                   language=p.get("language") or None, limit=int(p.get("limit", 300)),
                                   oldest_first=bool(p.get("oldest_first")))

    # ----- changing -----

    def set_settings(self, changes: dict) -> dict:
        changed = self._s.update(changes)
        if "start_with_windows" in changed:
            try:
                winutil.set_autostart(bool(changed["start_with_windows"]))
            except Exception:
                log.exception("Could not change start-with-Windows")
        self._e.apply_settings(changed)
        return self._s.all()

    def set_active_project(self, project_id: int) -> dict:
        self._s.update({"active_project": int(project_id)})
        self._gui.refresh_tray()
        return self._e.live()

    def set_language(self, language: str) -> dict:
        self._e.set_language(language)
        self._gui.refresh_tray()
        return self._e.live()

    def create_project(self, data: dict) -> dict:
        p = self._db.create_project(data.get("name", ""), language=data.get("language", "en"),
                                    remove_fillers=data.get("remove_fillers", True),
                                    capitalize=data.get("capitalize", True), rules=data.get("rules", []))
        self._gui.refresh_tray()
        return p

    def update_project(self, project_id: int, data: dict) -> dict:
        p = self._db.update_project(int(project_id), **data)
        if "language" in data and not self._e.model_ready_on_disk(data["language"]):
            self._e.download_model(data["language"])
        self._gui.refresh_tray()
        return p

    def delete_project(self, project_id: int) -> bool:
        self._db.delete_project(int(project_id))
        if self._s["active_project"] == int(project_id):
            self._s.update({"active_project": 1})
        self._gui.refresh_tray()
        return True

    def delete_item(self, item_id: int) -> bool:
        self._db.delete(int(item_id))
        return True

    def move_item(self, item_id: int, project_id: int) -> bool:
        self._db.move(int(item_id), int(project_id))
        return True

    def clear_history(self) -> int:
        return self._db.clear()

    def copy(self, text: str) -> bool:
        import pyperclip

        pyperclip.copy(text)
        return True

    def download_model(self, language: str) -> bool:
        self._e.download_model(language)
        return True

    def test_mic(self, seconds: float = 4.0) -> dict:
        """Records a few seconds from the selected mic and transcribes it."""
        from hushtype.audio import levels

        e = self._e
        if e.recorder is None:
            return {"error": "No microphone is open. Pick one above."}
        lang = e.live()["project"].get("language", "en")
        e.recorder.begin()
        time.sleep(seconds)
        audio = e.recorder.end()
        peak, avg = levels(audio)
        try:
            text = e.get_model(lang).transcribe(audio, lang)
        except Exception as ex:
            return {"peak": peak, "average": avg, "error": str(ex)}
        return {"peak": peak, "average": avg, "text": text}

    def cleanup(self, delete: bool) -> int:
        return self._e.cleanup(bool(delete))

    def cleanup_due(self) -> int:
        return self._e.cleanup_due()

    def open_data_folder(self) -> bool:
        winutil.open_folder(data_dir())
        return True

    def hide_window(self) -> bool:
        self._gui.hide_main()
        return True

    # ----- updates (only when the user asks) -----

    def check_update(self) -> dict:
        return self._gui.updater.check()

    def install_update(self) -> dict:
        self._gui.updater.install(on_ready_to_quit=self._gui.quit)
        return self._gui.updater.state

    def update_status(self) -> dict:
        return self._gui.updater.state

    def open_url(self, url: str) -> bool:
        import webbrowser

        if url.startswith("https://github.com/"):
            webbrowser.open(url)
        return True


class Gui:
    def __init__(self, settings: Settings, store: Store, engine: Engine, start_hidden: bool = False):
        self.settings = settings
        self.store = store
        self.engine = engine
        self.start_hidden = start_hidden
        self.api = Api(self)
        from hushtype.updater import Updater

        self.updater = Updater()
        self.main = None
        self.pill = None
        self.tray = None
        self._quitting = False
        self._pill_visible = False

    # ----- windows -----

    def build(self) -> None:
        import webview

        self.main = webview.create_window(
            "Hushtype", url=str(resource_path("ui", "index.html")), js_api=self.api,
            width=1180, height=800, min_size=(760, 560), background_color="#0B1220",
            hidden=self.start_hidden,
        )
        self.main.events.closing += self._on_closing
        x, y = self._pill_position()
        self.pill = webview.create_window(
            "Hushtype recording", url=str(resource_path("ui", "pill.html")), js_api=self.api,
            width=PILL_W, height=PILL_H, x=x, y=y, frameless=True, easy_drag=False, on_top=True,
            focus=False, resizable=False, transparent=True, hidden=True, shadow=False,
            background_color="#000000",
        )

    def _pill_position(self) -> tuple[int, int]:
        try:
            import webview

            s = webview.screens[0]
            return s.x + (s.width - PILL_W) // 2, s.y + s.height - PILL_H - 64
        except Exception:
            return 600, 900

    def _on_closing(self):
        if self._quitting:
            return True
        self.hide_main()
        return False  # keep running in the tray

    def show_main(self) -> None:
        if self.main:
            self.main.show()
            self.main.restore()

    def hide_main(self) -> None:
        if self.main:
            self.main.hide()

    def on_engine_state(self, state: str) -> None:
        """Shows the pill while recording/working/flashing, hides it otherwise."""
        if self.tray:
            self.tray.set_state(self.engine.live_state.state)
        if not self.pill:
            return
        want = self.settings["show_pill"] and (
            self.engine.live_state.state in ("recording", "working", "model") or state == "flash")
        if want and not self._pill_visible:
            self._pill_visible = True
            self.pill.show()
        if not want and state != "flash":
            threading.Thread(target=self._hide_pill_later, daemon=True).start()

    def _hide_pill_later(self) -> None:
        # Keep the pill up while a flash message ("Pasted") is showing.
        while True:
            live = self.engine.live()
            if live["state"] in ("recording", "working", "model"):
                return
            if not live["flash"]:
                break
            time.sleep(0.2)
        if self._pill_visible:
            self._pill_visible = False
            self.pill.hide()

    # ----- tray -----

    def refresh_tray(self) -> None:
        if self.tray:
            self.tray.refresh()

    def quit(self) -> None:
        self._quitting = True
        try:
            self.engine.stop()
        finally:
            if self.tray:
                self.tray.stop()
            for w in (self.pill, self.main):
                try:
                    w and w.destroy()
                except Exception:
                    pass

    # ----- run -----

    def run(self) -> None:
        import webview

        from hushtype.tray import Tray

        self.build()
        self.tray = Tray(self)
        threading.Thread(target=self.tray.run, daemon=True).start()

        def started():
            threading.Thread(target=self.engine.start, daemon=True).start()
            threading.Thread(target=self._review_loop, daemon=True).start()

        webview.start(started, private_mode=False, storage_path=str(data_dir() / "webview"))

    def _review_loop(self) -> None:
        """Checks hourly whether the weekly history prompt is due."""
        time.sleep(20)
        while not self._quitting:
            try:
                n = self.engine.cleanup_due()
                if n and self.main:
                    self.show_main()
                    self.main.evaluate_js(f"window.hushtype && window.hushtype.askCleanup({n})")
            except Exception:
                log.exception("History review check failed")
            time.sleep(3600)
