"""Hushtype: hold a key, speak, release, and the text is pasted where you type."""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
from pathlib import Path

from hushtype.cleanup import clean
from hushtype.config import load_config

log = logging.getLogger("hushtype")


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
            from hushtype.output import beep
            beep(True)

    def _on_up(self) -> None:
        if not self.ready.is_set():
            return
        audio = self.recorder.end()
        if self.cfg.beep:
            from hushtype.output import beep
            beep(False)
        if len(audio) < self.cfg.min_duration * 16000:
            self._state("idle")
            return
        self._state("working")
        self.jobs.put(audio)

    def _worker(self) -> None:
        from hushtype.output import paste_text

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
        from hushtype.audio import Recorder
        from hushtype.hotkey import PushToTalk
        from hushtype.transcriber import Transcriber

        try:
            log.info("Loading model '%s' (first run downloads it)...", self.cfg.model_name)
            self.transcriber = _make_transcriber(self.cfg)
            self.recorder = Recorder(self.cfg.mic, self.cfg.preroll)
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
        from hushtype.tray import Tray

        self.tray = Tray(on_quit=self.quit)

        def setup(icon):
            icon.visible = True
            threading.Thread(target=self._load, daemon=True).start()

        self.tray.run(setup)


def _make_transcriber(cfg):
    from hushtype.transcriber import Transcriber

    return Transcriber(cfg.model_name, cfg.device, cfg.compute_type, cfg.beam_size,
                       cfg.vocabulary, cfg.cpu_threads)


def _print_result(cfg, raw: str) -> None:
    print("RAW:  ", raw)
    print("CLEAN:", clean(raw, fillers=cfg.remove_fillers, replacements=cfg.replacements))


def transcribe_file(path: str, config_path: Path | None) -> None:
    """Debug helper: transcribe an audio file without the hotkey or tray."""
    from faster_whisper import decode_audio

    cfg = load_config(config_path)
    _print_result(cfg, _make_transcriber(cfg).transcribe(decode_audio(path, sampling_rate=16000)))


def list_devices() -> None:
    import sounddevice as sd

    from hushtype.audio import list_input_devices

    default = sd.default.device[0]
    print("Microphones (put part of a name in config.toml under [audio] mic):\n")
    for idx, name, api in list_input_devices():
        mark = "  <- Windows default" if idx == default else ""
        print(f"  [{idx:>2}] {name}  ({api}){mark}")


def mic_test(config_path: Path | None, seconds: float = 5.0) -> None:
    """Records a few seconds, reports the level, saves a WAV and transcribes it."""
    import time
    import wave

    import numpy as np

    from hushtype.audio import Recorder, levels

    cfg = load_config(config_path)
    rec = Recorder(cfg.mic, preroll=0)
    rec.start_stream()
    print("Loading model...")
    t = _make_transcriber(cfg)
    input(f"Press Enter, then speak for {seconds:.0f} seconds...")
    rec.begin()
    time.sleep(seconds)
    audio = rec.end()
    rec.close()

    peak, rms = levels(audio)
    print(f"\nLevel: peak {peak:.0f} dB, average {rms:.0f} dB")
    if peak < -40:
        print("  Too quiet: the mic is muted, the wrong device, or its volume is very low.")
    elif peak > -1:
        print("  Clipping: the input volume is too high.")
    else:
        print("  Level looks fine.")

    out = Path("hushtype_mic_test.wav").resolve()
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"Saved recording to {out} (play it to hear what Hushtype hears)\n")
    _print_result(cfg, t.transcribe(audio))


def main() -> None:
    parser = argparse.ArgumentParser(prog="hushtype", description=__doc__)
    parser.add_argument("--config", type=Path, help="path to config.toml")
    parser.add_argument("--file", help="transcribe an audio file and exit (for testing)")
    parser.add_argument("--list-devices", action="store_true", help="list microphones and exit")
    parser.add_argument("--mic-test", action="store_true",
                        help="record 5 seconds, show level, save WAV, transcribe")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    if args.list_devices:
        list_devices()
        return
    if args.mic_test:
        mic_test(args.config)
        return
    if args.file:
        transcribe_file(args.file, args.config)
        return
    App(args.config).run()


if __name__ == "__main__":
    main()
