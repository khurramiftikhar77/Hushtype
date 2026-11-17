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
LONG_AUDIO_SECONDS = 28

# Whisper imitates the style of its prompt. A well punctuated example makes it
# add commas, full stops and question marks on its own, without spoken commands.
PROMPTS = {
    "en": "Hi, thanks for sharing this. I really enjoyed reading it, and I agree. Shall we talk on Monday?",
    "ur": "السلام علیکم، آپ کیسے ہیں؟ میں ٹھیک ہوں، شکریہ۔ کل ملاقات کرتے ہیں۔",
    # Pakistani Punjabi in Shahmukhi, mixed with Urdu the way people speak it.
    "pa": "السلام علیکم، کی حال اے؟ میں ٹھیک آں، تسی سناؤ۔ کل ملدے آں، فیر گل کراں گے۔ بہت شکریہ جی۔",
    # Punjabi heard as Punjabi: Whisper writes Gurmukhi, converted to Shahmukhi after.
    "pa_gurmukhi": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ, ਕੀ ਹਾਲ ਏ? ਮੈਂ ਠੀਕ ਆਂ, ਤੁਸੀਂ ਸੁਣਾਓ। ਕੱਲ੍ਹ ਮਿਲਦੇ ਆਂ, ਫੇਰ ਗੱਲ ਕਰਾਂਗੇ। ਬਹੁਤ ਸ਼ੁਕਰੀਆ।",
    "de": "Hallo, danke für die Nachricht. Ich habe es gelesen und stimme zu. Sollen wir am Montag sprechen?",
    "hi": "नमस्ते, आप कैसे हैं? मैं ठीक हूँ, धन्यवाद। कल मिलते हैं।",
    "ar": "مرحباً، كيف حالك؟ أنا بخير، شكراً. نلتقي غداً.",
    "fa": "سلام، حال شما چطور است؟ من خوبم، ممنون. فردا همدیگر را می‌بینیم.",
    "ps": "سلام، تاسو څنګه یاست؟ زه ښه یم، مننه. سبا به سره ووینو.",
    "sd": "السلام عليڪم، توهان ڪيئن آهيو؟ مان ٺيڪ آهيان، مهرباني. سڀاڻي ملنداسين.",
}
# Whisper language code used for each Hushtype language. Whisper writes Punjabi
# in Gurmukhi, so Punjabi is decoded as Urdu (Urdu script) with a Punjabi prompt.
WHISPER_LANGUAGE = {"en": "en", "ur": "ur", "pa": "ur", "pa_gurmukhi": "pa"}


def model_on_disk(model_name: str) -> bool:
    """True when the model was downloaded before, so it can load offline."""
    try:
        from faster_whisper.utils import download_model

        download_model(model_name, local_files_only=True)
        return True
    except Exception:
        return False


def _model_folder(model_name: str):
    from pathlib import Path

    from faster_whisper.utils import _MODELS
    from huggingface_hub import constants

    repo = _MODELS.get(model_name, model_name)
    return Path(constants.HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))


def delete_model_files(model_name: str) -> int:
    """Removes a downloaded model from disk. Returns the bytes freed."""
    import shutil

    folder = _model_folder(model_name)
    if not folder.exists():
        return 0
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file() and not f.is_symlink())
    shutil.rmtree(folder, ignore_errors=True)
    return size


def model_cache_bytes(model_name: str) -> int:
    """Bytes of this model already in the download cache (finished or partial)."""
    from pathlib import Path

    try:
        folder = _model_folder(model_name)
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
        from faster_whisper import BatchedInferencePipeline

        # For long recordings: splits speech at natural pauses, transcribes each piece.
        self.pipeline = BatchedInferencePipeline(model=self.model)
        log.info("Loaded model %s in %.1fs", model_name, time.perf_counter() - t0)
        self.name = model_name
        self.beam_size = beam_size
        self.vocabulary = vocabulary or []
        self._lock = threading.Lock()  # one transcription at a time per model

    def _prompt(self, language: str, vocabulary: list[str] | None = None) -> str:
        base = PROMPTS.get(language, "")
        words = list(dict.fromkeys((vocabulary if vocabulary is not None else self.vocabulary) or []))[-40:]
        if words:
            base += " " + ", ".join(words) + "."
        return base

    def detect(self, audio: np.ndarray) -> dict[str, float]:
        """Language probabilities for the audio, e.g. {"en": 0.9, "ur": 0.05, ...}."""
        with self._lock:
            try:
                _lang, _p, all_probs = self.model.detect_language(audio, vad_filter=True)
            except Exception:  # e.g. only silence
                log.debug("Language detection failed", exc_info=True)
                return {}
        return dict(all_probs)

    def transcribe(self, audio: np.ndarray, language: str = "en", vocabulary: list[str] | None = None) -> str:
        """audio: mono float32 at 16 kHz. language: 'en' or 'ur'."""
        t0 = time.perf_counter()
        with self._lock:
            kwargs = dict(language=WHISPER_LANGUAGE.get(language, language), beam_size=self.beam_size,
                          # One pass only: retries at higher temperatures cost many
                          # seconds on a laptop CPU and rarely help short dictation.
                          temperature=0.0, initial_prompt=self._prompt(language, vocabulary))
            if len(audio) <= LONG_AUDIO_SECONDS * 16000:
                # Up to ~30 s: one window, the plain decoder is most accurate.
                segments, _info = self.model.transcribe(audio, vad_filter=True,
                                                        condition_on_previous_text=False, **kwargs)
            else:
                # Longer: split at natural pauses first. In Urdu tests the plain
                # decoder skipped whole sentences at the 30 s window boundary.
                segments, _info = self.pipeline.transcribe(audio, batch_size=4, **kwargs)
            segments = list(segments)
            kept = []
            for s in segments:
                if s.avg_logprob < MIN_AVG_LOGPROB and (s.no_speech_prob or 0) > MAX_NO_SPEECH_PROB:
                    log.info("Dropped unsure segment %r (logprob %.2f, no-speech %.2f)",
                             s.text, s.avg_logprob, s.no_speech_prob)
                    continue
                kept.append(s.text.strip())
        text = " ".join(kept).strip()
        if language == "pa_gurmukhi":
            from hushtype.shahmukhi import to_shahmukhi
            text = to_shahmukhi(text)
        log.info("Transcribed %.1fs of %s audio in %.1fs", len(audio) / 16000, language,
                 time.perf_counter() - t0)
        return text
