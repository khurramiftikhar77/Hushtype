"""Wraps faster-whisper. The model downloads once, then runs fully offline."""

from __future__ import annotations

import logging
import os
import time

import numpy as np

log = logging.getLogger(__name__)

# No usage statistics to Hugging Face, ever.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Segments this unsure are almost always Whisper guessing at noise
# ("You", "Thank you.", "Facebook.com"), so they are dropped instead of pasted.
MIN_AVG_LOGPROB = -1.0
MAX_NO_SPEECH_PROB = 0.6


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
        self.beam_size = beam_size
        self.prompt = ", ".join(vocabulary) if vocabulary else None

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: mono float32 at 16 kHz."""
        t0 = time.perf_counter()
        segments, _info = self.model.transcribe(
            audio,
            language="en",
            beam_size=self.beam_size,
            # One pass only. The default retries up to 6 times at higher
            # temperatures, which on a laptop CPU costs many seconds and
            # rarely helps with short dictation.
            temperature=0.0,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=self.prompt,
        )
        kept = []
        for s in segments:
            if s.avg_logprob < MIN_AVG_LOGPROB and s.no_speech_prob > MAX_NO_SPEECH_PROB:
                log.info("Dropped unsure segment %r (logprob %.2f, no-speech %.2f)",
                         s.text, s.avg_logprob, s.no_speech_prob)
                continue
            log.debug("Segment %r (logprob %.2f, no-speech %.2f)",
                      s.text, s.avg_logprob, s.no_speech_prob)
            kept.append(s.text.strip())
        text = " ".join(kept).strip()
        log.info("Transcribed %.1fs of audio in %.1fs", len(audio) / 16000, time.perf_counter() - t0)
        return text
