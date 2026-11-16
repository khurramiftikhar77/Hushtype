"""Wraps faster-whisper. Each model downloads once, then runs fully offline."""

from __future__ import annotations

import logging
import os
import threading
import time

import numpy as np

log = logging.getLogger(__name__)

# No usage statistics to Hugging Face, ever.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
# Plain HTTPS downloads into the cache, so the progress bar can watch them grow.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# Segments this unsure are almost always Whisper guessing at noise
# ("You", "Thank you.", "Facebook.com"), so they are dropped instead of pasted.
MIN_AVG_LOGPROB = -1.0
MAX_NO_SPEECH_PROB = 0.6

# Whisper imitates the style of its prompt. A well punctuated example makes it
# add commas, full stops and question marks on its own, without spoken commands.
PROMPTS = {
    "en": "Hi, thanks for sharing this. I really enjoyed reading it, and I agree. Shall we talk on Monday?",
    "ur": "السلام علیکم، آپ کیسے ہیں؟ میں ٹھیک ہوں، شکریہ۔ کل ملاقات کرتے ہیں۔",
    # Pakistani Punjabi in Shahmukhi, mixed with Urdu the way people speak it.
    "pa": "السلام علیکم، کی حال اے؟ میں ٹھیک آں، تسی سناؤ۔ کل ملدے آں، فیر گل کراں گے۔ بہت شکریہ جی۔",
}
# Whisper language code used for each Hushtype language. Whisper writes Punjabi
# in Gurmukhi, so Punjabi is decoded as Urdu (Urdu script) with a Punjabi prompt.
WHISPER_LANGUAGE = {"en": "en", "ur": "ur", "pa": "ur"}


def model_on_disk(model_name: str) -> bool:
    """True when the model was downloaded before, so it can load offline."""
    try:
        from faster_whisper.utils import download_model

        download_model(model_name, local_files_only=True)
        return True
    except Exception:
        return False


def model_cache_bytes(model_name: str) -> int:
    """Bytes of this model already in the download cache (finished or partial)."""
    from pathlib import Path

    try:
        from faster_whisper.utils import _MODELS
        from huggingface_hub import constants

        repo = _MODELS.get(model_name, model_name)
        folder = Path(constants.HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
        return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file() and not f.is_symlink())
    except Exception:
        return 0


class Transcriber:
    def __init__(self, model_name: str, device: str = "cpu", compute_type: str = "int8",
                 beam_size: int = 5, vocabulary: list[str] | None = None, cpu_threads: int = 0):
        from faster_whisper import WhisperModel  # heavy import, keep it lazy

        t0 = time.perf_counter()
        kwargs = dict(device=device, compute_type=compute_type, cpu_threads=cpu_threads)
        try:
            # Model already on disk: load it without touching the internet.
            self.model = WhisperModel(model_name, local_files_only=True, **kwargs)
        except Exception:
            # First use only: download the model (the app's one network connection).
            log.info("Model %s not on this computer yet, downloading it once...", model_name)
            self.model = WhisperModel(model_name, **kwargs)
        log.info("Loaded model %s in %.1fs", model_name, time.perf_counter() - t0)
        self.name = model_name
        self.beam_size = beam_size
        self.vocabulary = vocabulary or []
        self._lock = threading.Lock()  # one transcription at a time per model

    def _prompt(self, language: str) -> str:
        base = PROMPTS.get(language, "")
        if language == "en" and self.vocabulary:
            base += " " + ", ".join(self.vocabulary) + "."
        return base

    def transcribe(self, audio: np.ndarray, language: str = "en") -> str:
        """audio: mono float32 at 16 kHz. language: 'en' or 'ur'."""
        t0 = time.perf_counter()
        with self._lock:
            segments, _info = self.model.transcribe(
                audio,
                language=WHISPER_LANGUAGE.get(language, language),
                beam_size=self.beam_size,
                # One pass only. The default retries up to 6 times at higher
                # temperatures, which on a laptop CPU costs many seconds and
                # rarely helps with short dictation.
                temperature=0.0,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=self._prompt(language),
            )
            kept = []
            for s in segments:
                if s.avg_logprob < MIN_AVG_LOGPROB and s.no_speech_prob > MAX_NO_SPEECH_PROB:
                    log.info("Dropped unsure segment %r (logprob %.2f, no-speech %.2f)",
                             s.text, s.avg_logprob, s.no_speech_prob)
                    continue
                kept.append(s.text.strip())
        text = " ".join(kept).strip()
        log.info("Transcribed %.1fs of %s audio in %.1fs", len(audio) / 16000, language,
                 time.perf_counter() - t0)
        return text
