"""Microphone capture with a short pre-roll buffer.

The input stream stays open while the app runs so recording starts instantly
and the first word is not clipped. Audio is only kept while the hotkey is held
(plus a fraction of a second before it), nothing is stored on disk.
"""

from __future__ import annotations

import collections
import threading

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate: int = 16000, preroll: float = 0.3):
        self.sample_rate = sample_rate
        self._lock = threading.Lock()
        self._recording = False
        self._chunks: list[np.ndarray] = []
        # ~10 ms blocks, so preroll seconds = preroll*100 blocks
        self._blocksize = sample_rate // 100
        self._preroll: collections.deque[np.ndarray] = collections.deque(
            maxlen=max(1, int(preroll * 100))
        )
        self._stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self._blocksize,
            callback=self._callback,
        )

    def start_stream(self) -> None:
        self._stream.start()

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()

    def _callback(self, indata, frames, time_info, status) -> None:
        block = indata[:, 0].copy()
        with self._lock:
            if self._recording:
                self._chunks.append(block)
            else:
                self._preroll.append(block)

    def begin(self) -> None:
        with self._lock:
            self._chunks = list(self._preroll)
            self._preroll.clear()
            self._recording = True

    def end(self) -> np.ndarray:
        with self._lock:
            self._recording = False
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)
