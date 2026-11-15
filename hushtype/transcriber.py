"""Wraps faster-whisper. The model downloads once, then runs fully offline."""

from __future__ import annotations

import logging
import time

import numpy as np

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_name: str, device: str = "cpu", compute_type: str = "int8",
                 beam_size: int = 5, vocabulary: list[str] | None = None):
        from faster_whisper import WhisperModel  # heavy import, keep it lazy

        t0 = time.perf_counter()
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
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
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=self.prompt,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        log.info("Transcribed %.1fs of audio in %.1fs", len(audio) / 16000, time.perf_counter() - t0)
        return text
