"""Microphone capture with a short pre-roll buffer.

The input stream stays open while the app runs so recording starts instantly
and the first word is not clipped. Audio is only kept while the hotkey is held
(plus a fraction of a second before it), nothing is stored on disk.
"""

from __future__ import annotations

import collections
import logging
import threading

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

TARGET_RATE = 16000


def list_input_devices() -> list[tuple[int, str, str]]:
    """Returns (index, device name, host API name) for every input device."""
    apis = sd.query_hostapis()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append((i, d["name"], apis[d["hostapi"]]["name"]))
    return out


def resolve_device(spec: str | int | None) -> int | None:
    """Config value -> device index. Empty means the Windows default mic.

    A number is used as an index; text matches the first input device whose
    name contains it (case-insensitive), preferring the MME host API, which
    resamples for us.
    """
    if spec is None or spec == "":
        return None
    if isinstance(spec, int) or str(spec).isdigit():
        return int(spec)
    matches = [d for d in list_input_devices() if str(spec).lower() in d[1].lower()]
    if not matches:
        raise ValueError(f"No microphone matching '{spec}'. Run: start.bat --list-devices")
    matches.sort(key=lambda d: d[2] != "MME")
    return matches[0][0]


def device_name(index: int | None) -> str:
    info = sd.query_devices(index, "input")
    return info["name"]


def levels(audio: np.ndarray) -> tuple[float, float]:
    """(peak, rms) in dBFS. -inf for silence."""
    if audio.size == 0:
        return float("-inf"), float("-inf")
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio**2)))
    to_db = lambda x: 20 * np.log10(x) if x > 0 else float("-inf")  # noqa: E731
    return to_db(peak), to_db(rms)


def _resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or audio.size == 0:
        return audio
    n = int(round(len(audio) * dst / src))
    x_old = np.linspace(0, 1, len(audio), endpoint=False)
    x_new = np.linspace(0, 1, n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


class Recorder:
    def __init__(self, device: str | int | None = None, preroll: float = 0.3):
        self.device = resolve_device(device)
        self._lock = threading.Lock()
        self._recording = False
        self._chunks: list[np.ndarray] = []

        # Prefer 16 kHz directly; fall back to the device's own rate and resample.
        try:
            sd.check_input_settings(device=self.device, samplerate=TARGET_RATE, channels=1)
            self.rate = TARGET_RATE
        except Exception:
            self.rate = int(sd.query_devices(self.device, "input")["default_samplerate"])

        blocks_per_sec = 100
        self._blocksize = self.rate // blocks_per_sec
        self._preroll: collections.deque[np.ndarray] = collections.deque(
            maxlen=max(1, int(preroll * blocks_per_sec))
        )
        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.rate,
            channels=1,
            dtype="float32",
            blocksize=self._blocksize,
            callback=self._callback,
        )
        log.info("Microphone: %s (%d Hz)", device_name(self.device), self.rate)

    def start_stream(self) -> None:
        self._stream.start()

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("Audio status: %s", status)
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
        """Stops recording and returns mono float32 audio at 16 kHz."""
        with self._lock:
            self._recording = False
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = _resample(np.concatenate(chunks), self.rate, TARGET_RATE)
        peak, rms = levels(audio)
        log.info("Recorded %.1fs, level peak %.0f dB, average %.0f dB", len(audio) / TARGET_RATE, peak, rms)
        if peak < -40:
            log.warning("Very quiet recording. Check the microphone and its input volume.")
        return audio
