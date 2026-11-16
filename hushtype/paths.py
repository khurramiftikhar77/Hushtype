"""Where Hushtype keeps its settings, history and log."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("HUSHTYPE_HOME")
    if override:
        d = Path(override)
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Hushtype"
    else:
        d = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Hushtype"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path() -> Path:
    return data_dir() / "settings.json"


def db_path() -> Path:
    return data_dir() / "hushtype.db"


def log_path() -> Path:
    return data_dir() / "hushtype.log"


def resource_path(*parts: str) -> Path:
    """Files shipped with the app (UI, icon), also inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    pkg = base / "hushtype"
    return pkg.joinpath(*parts)
