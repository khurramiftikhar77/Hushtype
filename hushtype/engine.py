"""The core: hotkey -> microphone -> Whisper -> cleanup -> paste -> history.

The GUI only reads `live()` and calls the public methods; it never touches the
recorder or models directly. Every OS-facing piece is injectable for tests.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from hushtype.cleanup import clean
from hushtype.settings import LANGUAGES, MODEL_LANGUAGE, SOUTH_ASIAN, Settings, now_iso
from hushtype.store import INBOX_ID, Store

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
AUTO_ENGLISH_CONFIDENCE = 0.7
FLASH_SECONDS = 1.6


@dataclass
class Job:
    audio: np.ndarray
    project: dict
    language: str
    hwnd: int
    app: str
    duration: float
    from_app: bool = False  # started with the button in Hushtype's window: copy, don't paste


@dataclass
class Live:
    state: str = "loading"  # loading | idle | recording | working | model | error
    message: str = "Starting..."
    started: float = 0.0
    hands_free: bool = False
    project: dict = field(default_factory=dict)
    language: str = "en"


class Engine:
    def __init__(self, settings: Settings, store: Store, *,
                 recorder_factory: Callable | None = None,
                 transcriber_factory: Callable | None = None,
                 hotkeys_factory: Callable | None = None,
                 paste: Callable[[str, bool], None] | None = None,
                 copy: Callable[[str], None] | None = None,
                 model_bytes: Callable[[str], int] | None = None,
                 foreground: Callable[[], tuple[int, str, str]] | None = None,
                 focus: Callable[[int], None] | None = None,
                 model_on_disk: Callable[[str], bool] | None = None,
                 delete_model: Callable[[str], int] | None = None,
                 on_state: Callable[[str], None] | None = None):
        self.settings = settings
        self.store = store
        self._recorder_factory = recorder_factory
        self._transcriber_factory = transcriber_factory
        self._hotkeys_factory = hotkeys_factory
        self._paste = paste
        self._copy = copy
        self._model_bytes = model_bytes
        self.downloads: dict[str, dict] = {}  # language -> {"done": bytes, "total": bytes}
        self._foreground = foreground
        self._focus = focus
        self._model_on_disk = model_on_disk
        self._delete_model = delete_model
        self.on_state = on_state or (lambda s: None)

        self.live_state = Live()
        self._flash: tuple[str, str, float] | None = None  # (kind, text, until)
        self.recorder = None
        self.hotkeys = None
        self.models: dict[str, object] = {}  # model name -> Transcriber (shared by languages)
        self._model_lock = threading.Lock()
        self.loading_models: set[str] = set()
        self.model_errors: dict[str, str] = {}
        self._jobs: queue.Queue = queue.Queue()
        self._target: dict | None = None
        self.last_text: str | None = None
        self._lock = threading.RLock()

    # ---------- lifecycle ----------

    def start(self) -> None:
        """Opens the mic and hotkey, then loads the English model. Call off the UI thread."""
        threading.Thread(target=self._worker, daemon=True, name="hushtype-worker").start()
        self._open_recorder()
        self._open_hotkeys()
        lang = self._active_project()["language"]
        try:
            self.get_model("en")
            for extra in self._models_for(lang):
                if extra != "en" and self.model_ready_on_disk(extra):
                    self.get_model(extra)
        except Exception as e:
            log.exception("Could not load the speech model")
            self._set("error", f"Could not load the speech model: {e}")
            return
        if self.live_state.state in ("loading", "model"):
            self._set("idle", "Ready")

    def stop(self) -> None:
        self._jobs.put(None)
        if self.hotkeys:
            self.hotkeys.stop()
        if self.recorder:
            try:
                self.recorder.close()
            except Exception:
                pass

    def _open_recorder(self) -> None:
        if self.recorder:
            try:
                self.recorder.close()
            except Exception:
                pass
            self.recorder = None
        try:
            self.recorder = self._recorder_factory(self.settings["mic"], self.settings["preroll"])
            self.recorder.start_stream()
        except Exception as e:
            log.exception("Microphone failed")
            self.recorder = None
            self._set("error", f"Microphone not available: {e}")

    def _open_hotkeys(self) -> None:
        if self.hotkeys:
            self.hotkeys.stop()
        actions = {"start": self.begin_recording, "stop": self.finish_recording,
                   "cancel": self.cancel_recording, "toggle_language": self.toggle_language,
                   "repaste": self.repaste, "hands_free": self._hands_free_on}
        self.hotkeys = self._hotkeys_factory(self.settings["hotkey"], actions,
                                             self.settings["hands_free"],
                                             self.settings["language_switch_key"])
        self.hotkeys.start()

    def apply_settings(self, changed: dict) -> None:
        """Reacts to settings saved from the GUI."""
        if "mic" in changed or "preroll" in changed:
            self._open_recorder()
            if self.recorder and self.live_state.state == "error":
                self._set("idle", "Ready")
        if {"hotkey", "hands_free", "language_switch_key"} & changed.keys():
            self._open_hotkeys()
        if {"en_model", "ur_model", "models", "detect_model", "languages_enabled"} & changed.keys():
            self._unload_unused()

    # ---------- state ----------

    def _set(self, state: str, message: str = "") -> None:
        with self._lock:
            self.live_state.state = state
            self.live_state.message = message
        self.on_state(state)

    def flash(self, kind: str, text: str) -> None:
        """A short message on the pill: 'pasted', 'warn', 'info'."""
        self._flash = (kind, text, time.monotonic() + FLASH_SECONDS)
        self.on_state("flash")

    def live(self) -> dict:
        s = self.live_state
        flash = None
        if self._flash and self._flash[2] > time.monotonic():
            flash = {"kind": self._flash[0], "text": self._flash[1]}
        project = s.project if s.state in ("recording", "working") else self._active_project()
        return {
            "state": s.state,
            "message": s.message,
            "elapsed": (time.monotonic() - s.started) if s.state == "recording" else 0.0,
            "level": self.recorder.level if (self.recorder and s.state == "recording") else 0.0,
            "hands_free": s.hands_free,
            "max_seconds": float(self.settings["max_seconds"] or 0),
            "from_app": bool(self._target and self._target.get("from_app")),
            "project": {k: project.get(k) for k in ("id", "name", "color", "language")},
            "language": s.language if s.state in ("recording", "working") else project.get("language", "en"),
            "flash": flash,
            "version": self.store.version,
            "loading_models": sorted(self.loading_models),
            "downloads": {k: dict(v) for k, v in self.downloads.items()},
        }

    # ---------- projects & models ----------

    def _active_project(self) -> dict:
        p = self.store.project(self.settings["active_project"])
        if p is None:
            self.settings.update({"active_project": INBOX_ID})
            p = self.store.project(INBOX_ID)
        return p

    def model_name(self, language: str) -> str:
        slot = MODEL_LANGUAGE.get(language, language)
        if slot in ("en", "ur", "detect"):
            return self.settings[f"{slot}_model"]
        return self.settings["models"].get(slot, "large-v3-turbo")

    def model_ready_on_disk(self, language: str) -> bool:
        name = self.model_name(language)
        if name in self.models:
            return True
        return bool(self._model_on_disk and self._model_on_disk(name))

    def enabled_languages(self) -> list[str]:
        langs = [l for l in self.settings["languages_enabled"] if l in LANGUAGES and l != "auto"]
        return langs or ["en"]

    def _needed_models(self) -> set[str]:
        names = {self.model_name(l) for l in self.enabled_languages()}
        names.add(self.model_name("en"))
        if self._active_project()["language"] == "auto":
            names.add(self.model_name("detect"))
        return names

    def _unload_unused(self) -> None:
        """Frees memory held by models no enabled language uses any more."""
        with self._model_lock:
            keep = self._needed_models() | {self.model_name("detect")}
            for name in list(self.models):
                if name not in keep:
                    log.info("Unloading model %s", name)
                    self.models.pop(name, None)

    def remove_model(self, language: str) -> int:
        """Deletes a language's model from disk (and memory). Returns bytes freed."""
        name = self.model_name(language)
        with self._model_lock:
            self.models.pop(name, None)
        if not self._delete_model:
            return 0
        freed = self._delete_model(name)
        log.info("Removed model %s (%.0f MB)", name, freed / 1e6)
        return freed

    def get_model(self, language: str):
        """Returns the loaded model for a language, loading (or downloading) it once."""
        language = MODEL_LANGUAGE.get(language, language)  # Punjabi uses the Urdu model
        with self._model_lock:
            name = self.model_name(language)
            if name in self.models:
                return self.models[name]
            self.loading_models.add(language)
            downloading = not self.model_ready_on_disk(language)
            label = LANGUAGES.get(language, language)
            prev = self.live_state.state
            if prev in ("idle", "loading", "model", "working"):
                self._set("model", f"{'Downloading' if downloading else 'Loading'} the {label} model...")
            if downloading:
                self._watch_download(language, name)
            try:
                t = self._transcriber_factory(name, self.settings["beam_size"],
                                              self.settings["vocabulary"], self.settings["cpu_threads"])
                self.models[name] = t
                self.model_errors.pop(language, None)
                return t
            except Exception as e:
                self.model_errors[language] = str(e)
                raise
            finally:
                self.loading_models.discard(language)
                self.downloads.pop(language, None)
                if self.live_state.state == "model":
                    self._set("working" if prev == "working" else "idle", "Ready")

    @staticmethod
    def _models_for(language: str) -> list[str]:
        """Model slots a language needs: Auto needs the detector and both writers."""
        return ["detect", "en", "ur"] if language == "auto" else [language]

    def _language_order(self) -> list[str]:
        return ["auto"] + self.enabled_languages()

    def detect_language(self, audio) -> str:
        """Auto mode: English or (Urdu / Punjabi, as chosen in Settings)."""
        probs = self.get_model("detect").detect(audio)
        english = probs.get("en", 0.0)
        south = sum(probs.get(k, 0.0) for k in SOUTH_ASIAN)
        other = self.settings["auto_other"] if self.settings["auto_other"] in ("ur", "pa", "hi") else "ur"
        # English only when the detector is clearly sure: short Urdu was sometimes
        # mistaken for English, never the other way round. 0.7 scored 60/60 Urdu
        # and 60/60 English on 3 s of real speech (Google FLEURS).
        if english >= AUTO_ENGLISH_CONFIDENCE:
            choice = "en"
        else:
            # Other enabled languages (Arabic, Persian...) win if they clearly beat
            # the Urdu/Hindi/Punjabi group; that group is one sound for the detector.
            extra = {l: probs.get(l, 0.0) for l in self.enabled_languages() if l not in SOUTH_ASIAN + ("en",)}
            best = max(extra, key=extra.get) if extra else None
            choice = best if best and extra[best] > south else other
        log.info("Auto language: %s (English %.2f, Urdu/Hindi/Punjabi %.2f)", choice, english, south)
        return choice

    def _watch_download(self, language: str, name: str) -> None:
        """Tracks download progress by watching the model's cache folder grow."""
        from hushtype.settings import MODEL_BYTES

        total = MODEL_BYTES.get(name, 0)
        if not (self._model_bytes and total):
            return
        start = self._model_bytes(name)
        self.downloads[language] = {"done": 0, "total": total}

        def loop():
            while language in self.loading_models:
                try:
                    done = max(0, self._model_bytes(name) - start)
                    if language in self.downloads:
                        self.downloads[language]["done"] = min(done, total)
                except Exception:
                    pass
                time.sleep(0.5)

        threading.Thread(target=loop, daemon=True).start()

    def download_model(self, language: str) -> None:
        def run():
            try:
                for slot in self._models_for(language):
                    self.get_model(slot)
                self.flash("pasted", f"{LANGUAGES.get(language, language)} ready")
            except Exception as e:
                log.exception("Model download failed")
                self.flash("warn", f"Download failed: {e}")
        threading.Thread(target=run, daemon=True).start()

    # ---------- hotkey actions ----------

    def _pick_target(self) -> dict:
        hwnd, title, exe = self._foreground() if self._foreground else (0, "", "")
        from hushtype.winutil import friendly_app

        pid = self.store.match_rule(f"{exe} {title}")
        project = (self.store.project(pid) if pid else None) or self._active_project()
        return {"hwnd": hwnd, "app": friendly_app(title, exe), "project": project}

    def begin_recording(self, from_app: bool = False) -> None:
        state = self.live_state.state
        if state in ("loading",):
            self.flash("info", "Still starting, one moment")
            return
        if self.recorder is None:
            self.flash("warn", "No microphone. Check Settings.")
            return
        if from_app:  # the button in Hushtype's own window: no app rules, no pasting
            target = {"hwnd": 0, "app": "Hushtype", "project": self._active_project(), "from_app": True}
        else:
            target = self._pick_target()
        self._target = target
        self.recorder.begin()
        if self.settings["beep"]:
            from hushtype.output import beep
            beep(True)
        with self._lock:
            self.live_state.started = time.monotonic()
            self.live_state.hands_free = False
            self.live_state.project = target["project"]
            self.live_state.language = target["project"]["language"]
        self._set("recording", "Listening")
        self._start_limit_watch(self.live_state.started)

    def _start_limit_watch(self, started: float) -> None:
        """Stops the recording by itself when it reaches the maximum length."""
        limit = float(self.settings["max_seconds"] or 0)
        if limit <= 0:
            return

        def watch():
            while self.live_state.state == "recording" and self.live_state.started == started:
                if time.monotonic() - started >= limit:
                    log.info("Recording reached the %ss limit, stopping", int(limit))
                    self.finish_recording()
                    self.flash("info", "Time limit reached. Text copied")
                    return
                time.sleep(0.1)

        threading.Thread(target=watch, daemon=True).start()

    def _hands_free_on(self) -> None:
        with self._lock:
            self.live_state.hands_free = True
        self.on_state("recording")

    def cancel_recording(self) -> None:
        if self.live_state.state != "recording":
            return
        if self.recorder:
            self.recorder.cancel()
        self._target = None
        with self._lock:
            self.live_state.hands_free = False
        self._set("idle", "Ready")

    def finish_recording(self) -> None:
        if self.live_state.state != "recording" or self.recorder is None:
            return
        audio = self.recorder.end()
        if self.settings["beep"]:
            from hushtype.output import beep
            beep(False)
        target, self._target = self._target, None
        with self._lock:
            self.live_state.hands_free = False
        duration = len(audio) / SAMPLE_RATE
        if duration < self.settings["min_duration"] or target is None:
            self._set("idle", "Ready")
            return
        self._set("working", "Transcribing")
        self._jobs.put(Job(audio=audio, project=target["project"], language=self.live_state.language,
                           hwnd=target["hwnd"], app=target["app"], duration=duration,
                           from_app=bool(target.get("from_app"))))

    def toggle_language(self) -> None:
        """Cycles the active project's language: English, Urdu, Punjabi."""
        p = self._active_project()
        order = self._language_order()
        new = order[(order.index(p["language"]) + 1) % len(order)] if p["language"] in order else "en"
        self.store.update_project(p["id"], language=new)
        self.flash("info", f"{p['name']}: {LANGUAGES[new]}")
        if not all(self.model_ready_on_disk(m) for m in self._models_for(new)):
            self.download_model(new)

    def set_language(self, language: str) -> None:
        p = self._active_project()
        self.store.update_project(p["id"], language=language)
        if not all(self.model_ready_on_disk(m) for m in self._models_for(language)):
            self.download_model(language)

    def repaste(self) -> None:
        """Modifier + V: copies the last dictation again (and pastes it if auto-paste is on)."""
        if not self.last_text:
            last = self.store.last()
            self.last_text = last["text"] if last else None
        if not self.last_text:
            self.flash("info", "Nothing to copy yet")
        elif self.settings["auto_paste"] and self._paste:
            self._paste(self.last_text, self.settings["keep_on_clipboard"])
            self.flash("pasted", "Pasted again")
        elif self._copy:
            self._copy(self.last_text)
            self.flash("pasted", "Copied again. Press Ctrl+V")

    # ---------- worker ----------

    def _worker(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._process(job)
            except Exception as e:
                log.exception("Transcription failed")
                self.flash("warn", f"Something went wrong: {e}")
            finally:
                if self._jobs.empty() and self.live_state.state in ("working", "model"):
                    self._set("idle", "Ready")

    def _process(self, job: Job) -> dict | None:
        t0 = time.perf_counter()
        language = job.language
        detected = language == "auto"
        if detected:
            language = self.detect_language(job.audio)
            with self._lock:
                self.live_state.language = language  # the pill and theme follow the detected language
        model = self.get_model(language)
        self._set("working", "Transcribing")
        s = self.settings
        vocabulary = list(s["vocabulary"]) + list(s["learned_words"])
        raw = model.transcribe(job.audio, language, vocabulary=vocabulary)
        p = job.project
        replacements = {**s["learned_replacements"], **s["replacements"]}  # your own rules win
        text = clean(raw, language=language, fillers=p["remove_fillers"], capitalize=p["capitalize"],
                     spoken_commands=s["spoken_commands"], replacements=replacements,
                     snippets=s["snippets"])
        took = time.perf_counter() - t0
        if not text:
            self.flash("warn", "Didn't catch that. Try again")
            return None
        if s["trailing_space"] and not text.endswith("\n"):
            text += " "
        self.last_text = text
        words = len(text.split())
        plural = "s" if words != 1 else ""
        if detected:
            plural += f" · {LANGUAGES[language]}"
        if job.from_app:
            if self._copy:
                self._copy(text)
            self.flash("pasted", f"Copied · {words} word{plural} · Ctrl+V to paste")
        elif s["auto_paste"]:
            if self._focus:
                self._focus(job.hwnd)
            if self._paste:
                self._paste(text, s["keep_on_clipboard"])
            self.flash("pasted", f"Pasted · {words} word{plural}")
        else:
            if self._copy:
                self._copy(text)
            self.flash("pasted", f"Copied · {words} word{plural} · Ctrl+V to paste")
        if s["learn_names"] and language == "en":
            self._learn_names(text)
        if s["save_history"]:
            return self.store.add(project_id=p["id"], language=language, duration=round(job.duration, 2),
                                  process_time=round(took, 2), text=text.strip(), raw_text=raw, app=job.app)
        return None

    # ---------- learning ----------

    def _learn_names(self, text: str) -> None:
        from hushtype.learning import candidate_names

        known = {w.lower() for w in self.settings["vocabulary"] + self.settings["learned_words"]}
        names = [n for n in candidate_names(text) if n.lower() not in known]
        reached = self.store.bump_words(names) if names else []
        if reached:
            words = (self.settings["learned_words"] + reached)[-60:]
            self.settings.update({"learned_words": words})
            log.info("Learned names: %s", ", ".join(reached))

    def learn_from_edit(self, old: str, new: str) -> list[tuple[str, str]]:
        """Called when the user corrects a dictation in History."""
        from hushtype.learning import extract_corrections

        if not self.settings["learn_from_edits"]:
            return []
        fixes = extract_corrections(old, new)
        if fixes:
            learned = dict(self.settings["learned_replacements"])
            for wrong, right in fixes:
                learned[wrong] = right
            self.settings.update({"learned_replacements": learned})
            words = list(self.settings["learned_words"])
            for _wrong, right in fixes:
                if right[:1].isupper() and right not in words and right not in self.settings["vocabulary"]:
                    words.append(right)
            self.settings.update({"learned_words": words[-60:]})
            log.info("Learned corrections: %s", fixes)
        return fixes

    # ---------- history review ----------

    def cleanup_due(self) -> int:
        """Number of old dictations to offer for deletion, or 0 if no prompt is due."""
        days = int(self.settings["review_days"] or 0)
        if days <= 0:
            return 0
        from datetime import datetime, timedelta

        try:
            last = datetime.fromisoformat(self.settings["last_review"])
        except Exception:
            last = None
        if last and datetime.now(last.tzinfo) - last < timedelta(days=days):
            return 0
        return self.store.count_older_than(days)

    def cleanup(self, delete: bool) -> int:
        n = self.store.delete_older_than(int(self.settings["review_days"] or 7)) if delete else 0
        self.settings.update({"last_review": now_iso()})
        return n


def default_engine(settings: Settings, store: Store, on_state=None) -> Engine:
    """Engine wired to the real microphone, keyboard, clipboard and Whisper."""
    from hushtype import winutil
    from hushtype.audio import Recorder
    from hushtype.hotkey import Hotkeys
    from hushtype.output import copy_text, paste_text
    from hushtype.transcriber import Transcriber, delete_model_files, model_cache_bytes, model_on_disk

    return Engine(
        settings, store,
        recorder_factory=lambda mic, preroll: Recorder(mic, preroll),
        transcriber_factory=lambda name, beam, vocab, threads: Transcriber(
            name, beam_size=beam, vocabulary=vocab, cpu_threads=threads),
        hotkeys_factory=lambda key, actions, hands_free, combos: Hotkeys(key, actions, hands_free, combos),
        paste=paste_text,
        copy=copy_text,
        model_bytes=model_cache_bytes,
        foreground=winutil.foreground_window,
        focus=winutil.focus_window,
        model_on_disk=model_on_disk,
        delete_model=delete_model_files,
        on_state=on_state,
    )
