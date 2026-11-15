"""LocalFlow: hold a key, speak, release, and the text is pasted where you type."""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
from pathlib import Path

from localflow.cleanup import clean
from localflow.config import load_config

log = logging.getLogger("localflow")


class App:
    def __init__(self, config_path: Path | None = None):
        self.cfg = load_config(config_path)
        self.jobs: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.tray = None
        self.recorder = None
        self.transcriber = None
        self.hotkey = None

    # state shown in tray
    def _state(self, s: str) -> None:
        if self.tray:
            self.tray.set_state(s)

    def _on_down(self) -> None:
        if not self.ready.is_set():
            return
        self.recorder.begin()
        self._state("recording")
        if self.cfg.beep:
            from localflow.output import beep
            beep(True)

    def _on_up(self) -> None:
        if not self.ready.is_set():
            return
        audio = self.recorder.end()
        if self.cfg.beep:
            from localflow.output import beep
            beep(False)
        if len(audio) < self.cfg.min_duration * self.cfg.sample_rate:
            self._state("idle")
            return
        self._state("working")
        self.jobs.put(audio)

    def _worker(self) -> None:
        from localflow.output import paste_text

        while True:
            audio = self.jobs.get()
            if audio is None:
                return
            try:
                raw = self.transcriber.transcribe(audio)
                text = clean(raw, fillers=self.cfg.remove_fillers,
                             replacements=self.cfg.replacements)
                log.info("Text: %r", text)
                if text:
                    if self.cfg.trailing_space:
                        text += " "
                    paste_text(text)
            except Exception:
                log.exception("Transcription failed")
            finally:
                if self.jobs.empty():
                    self._state("idle")

    def _load(self) -> None:
        from localflow.audio import Recorder
        from localflow.hotkey import PushToTalk
        from localflow.transcriber import Transcriber

        try:
            log.info("Loading model '%s' (first run downloads it)...", self.cfg.model_name)
            self.transcriber = Transcriber(
                self.cfg.model_name, self.cfg.device, self.cfg.compute_type,
                self.cfg.beam_size, self.cfg.vocabulary,
            )
            self.recorder = Recorder(self.cfg.sample_rate, self.cfg.preroll)
            self.recorder.start_stream()
            self.hotkey = PushToTalk(self.cfg.hotkey, self._on_down, self._on_up)
            self.hotkey.start()
            threading.Thread(target=self._worker, daemon=True).start()
            self.ready.set()
            self._state("idle")
            log.info("Ready. Hold %s and speak.", self.cfg.hotkey)
        except Exception:
            log.exception("Startup failed")
            self.quit()

    def quit(self) -> None:
        self.jobs.put(None)
        if self.hotkey:
            self.hotkey.stop()
        if self.recorder:
            self.recorder.close()
        if self.tray:
            self.tray.stop()

    def run(self) -> None:
        from localflow.tray import Tray

        self.tray = Tray(on_quit=self.quit)

        def setup(icon):
            icon.visible = True
            threading.Thread(target=self._load, daemon=True).start()

        self.tray.run(setup)


def transcribe_file(path: str, config_path: Path | None) -> None:
    """Debug helper: transcribe an audio file without the hotkey or tray."""
    from faster_whisper import decode_audio

    from localflow.transcriber import Transcriber

    cfg = load_config(config_path)
    t = Transcriber(cfg.model_name, cfg.device, cfg.compute_type, cfg.beam_size, cfg.vocabulary)
    raw = t.transcribe(decode_audio(path, sampling_rate=16000))
    print("RAW:  ", raw)
    print("CLEAN:", clean(raw, fillers=cfg.remove_fillers, replacements=cfg.replacements))


def main() -> None:
    parser = argparse.ArgumentParser(prog="localflow", description=__doc__)
    parser.add_argument("--config", type=Path, help="path to config.toml")
    parser.add_argument("--file", help="transcribe an audio file and exit (for testing)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    if args.file:
        transcribe_file(args.file, args.config)
        return
    App(args.config).run()


if __name__ == "__main__":
    main()
