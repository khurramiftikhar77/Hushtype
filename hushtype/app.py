"""Hushtype: hold a key, speak, release, and the text is typed where you are."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

from hushtype import BUILD, __version__
from hushtype.cleanup import clean
from hushtype.paths import log_path

log = logging.getLogger("hushtype")


def setup_logging(verbose: bool) -> None:
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stdout is not None:  # no console in the installed (windowed) app
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    for noisy in ("httpx", "huggingface_hub", "faster_whisper", "urllib3", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING if not verbose else logging.INFO)


# ---------- command-line helpers ----------

def _transcriber(language: str):
    from hushtype.settings import Settings
    from hushtype.transcriber import Transcriber

    s = Settings()
    return s, Transcriber(s[f"{language}_model"], beam_size=s["beam_size"], vocabulary=s["vocabulary"],
                          cpu_threads=s["cpu_threads"])


def _print_result(settings, raw: str, language: str) -> None:
    print("RAW:  ", raw)
    print("CLEAN:", clean(raw, language=language, replacements=settings["replacements"],
                          snippets=settings["snippets"], spoken_commands=settings["spoken_commands"]))


def transcribe_file(path: str, language: str) -> None:
    from faster_whisper import decode_audio

    s, t = _transcriber(language)
    _print_result(s, t.transcribe(decode_audio(path, sampling_rate=16000), language), language)


def list_devices() -> None:
    import sounddevice as sd

    from hushtype.audio import list_input_devices

    default = sd.default.device[0]
    print("Microphones (choose one in Settings inside the app):\n")
    for idx, name, api in list_input_devices():
        mark = "  <- Windows default" if idx == default else ""
        print(f"  [{idx:>2}] {name}  ({api}){mark}")


def mic_test(language: str, seconds: float = 5.0) -> None:
    """Records a few seconds, reports the level, saves a WAV and transcribes it."""
    import time
    import wave

    import numpy as np

    from hushtype.audio import Recorder, levels

    s, t = _transcriber(language)
    rec = Recorder(s["mic"], preroll=0)
    rec.start_stream()
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
    _print_result(s, t.transcribe(audio, language), language)


def self_test(out_path: str) -> int:
    """Checks that a packaged build can load everything. Used by the installer build."""
    import tempfile
    import traceback

    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            result = fn()
            lines.append(f"OK   {name}{': ' + str(result) if result is not None else ''}")
        except Exception:
            ok = False
            lines.append(f"FAIL {name}\n{traceback.format_exc()}")

    def transcribe_silence():
        import numpy as np

        from hushtype.transcriber import Transcriber

        t = Transcriber("tiny.en")
        return repr(t.transcribe(np.zeros(16000, dtype=np.float32), "en"))

    def store_roundtrip():
        from hushtype.store import Store

        with tempfile.TemporaryDirectory() as d:
            s = Store(Path(d) / "t.db")
            s.create_project("Test", rules=["x"])
            n = len(s.projects())
            s.close()
            return n

    check("version", lambda: f"{__version__} ({BUILD})")
    check("ui files", lambda: [p.name for p in __import__("hushtype.paths", fromlist=["x"]).resource_path("ui").iterdir()])
    check("numpy", lambda: __import__("numpy").__version__)
    check("ctranslate2", lambda: __import__("ctranslate2").__version__)
    check("onnxruntime", lambda: __import__("onnxruntime").__version__)
    check("av", lambda: __import__("av").__version__)
    check("sounddevice", lambda: __import__("sounddevice").get_portaudio_version()[1])
    check("pynput", lambda: __import__("pynput.keyboard", fromlist=["x"]).Listener.__name__)
    check("pystray", lambda: __import__("pystray").Icon.__module__)
    check("webview", lambda: __import__("webview").__name__)
    check("pyperclip", lambda: __import__("pyperclip").__name__)
    check("store", store_roundtrip)
    check("whisper tiny.en + VAD", transcribe_silence)
    lines.append("RESULT " + ("PASS" if ok else "FAIL"))
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1


# ---------- the app ----------

def run_app(background: bool) -> None:
    from hushtype import winutil
    from hushtype.engine import default_engine
    from hushtype.gui import Gui
    from hushtype.settings import Settings
    from hushtype.store import Store

    instance = winutil.SingleInstance()
    if instance.already_running:
        log.info("Hushtype is already running; bringing it to the front")
        instance.notify_running()
        return

    settings = Settings()
    store = Store()
    if settings.first_run and settings["start_with_windows"]:
        try:
            winutil.set_autostart(True)
        except Exception:
            log.exception("Could not enable start-with-Windows")

    gui: Gui | None = None
    engine = default_engine(settings, store, on_state=lambda s: gui and gui.on_engine_state(s))
    gui = Gui(settings, store, engine, start_hidden=background)
    instance.listen(gui.show_main)
    log.info("Hushtype %s (%s) starting", __version__, BUILD)
    gui.run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="hushtype", description=__doc__)
    parser.add_argument("--background", action="store_true", help="start in the tray without opening the window")
    parser.add_argument("--file", help="transcribe an audio file and exit (for testing)")
    parser.add_argument("--language", default="en", choices=["en", "ur"], help="language for --file / --mic-test")
    parser.add_argument("--list-devices", action="store_true", help="list microphones and exit")
    parser.add_argument("--mic-test", action="store_true", help="record 5 seconds, show level, save WAV, transcribe")
    parser.add_argument("--self-test", metavar="OUT", help="check the installation and write a report to OUT")
    parser.add_argument("--version", action="version", version=f"Hushtype {__version__} ({BUILD})")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test(args.self_test))
    setup_logging(args.verbose)
    if args.list_devices:
        list_devices()
    elif args.mic_test:
        mic_test(args.language)
    elif args.file:
        transcribe_file(args.file, args.language)
    else:
        run_app(args.background)


if __name__ == "__main__":
    main()
