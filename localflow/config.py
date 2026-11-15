"""Loads settings from config.toml, falling back to defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass
class Config:
    hotkey: str = "alt_r"
    model_name: str = "small.en"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    sample_rate: int = 16000
    min_duration: float = 0.4
    preroll: float = 0.3
    remove_fillers: bool = True
    trailing_space: bool = True
    beep: bool = True
    vocabulary: list[str] = field(default_factory=list)
    replacements: dict[str, str] = field(default_factory=dict)


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_PATH
    cfg = Config()
    if not path.exists():
        return cfg
    with open(path, "rb") as f:
        data = tomllib.load(f)

    hotkey = data.get("hotkey", {})
    model = data.get("model", {})
    audio = data.get("audio", {})
    output = data.get("output", {})

    cfg.hotkey = hotkey.get("key", cfg.hotkey)
    cfg.model_name = model.get("name", cfg.model_name)
    cfg.device = model.get("device", cfg.device)
    cfg.compute_type = model.get("compute_type", cfg.compute_type)
    cfg.beam_size = int(model.get("beam_size", cfg.beam_size))
    cfg.sample_rate = int(audio.get("sample_rate", cfg.sample_rate))
    cfg.min_duration = float(audio.get("min_duration", cfg.min_duration))
    cfg.preroll = float(audio.get("preroll", cfg.preroll))
    cfg.remove_fillers = bool(output.get("remove_fillers", cfg.remove_fillers))
    cfg.trailing_space = bool(output.get("trailing_space", cfg.trailing_space))
    cfg.beep = bool(output.get("beep", cfg.beep))
    cfg.vocabulary = list(data.get("vocabulary", {}).get("words", []))
    cfg.replacements = {str(k): str(v) for k, v in data.get("replacements", {}).items()}
    return cfg
