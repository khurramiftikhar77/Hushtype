"""Manual updates from GitHub Releases.

Nothing here runs on its own: Hushtype only contacts GitHub when you press
"Check for updates" in Settings. The check reads the latest release of the
public repository; installing downloads its Hushtype-Setup-x.y.z.exe over
HTTPS, checks the size, and runs it silently. The installer closes Hushtype,
replaces the program files and starts it again. Your settings, history and
downloaded models are kept (they live outside the program folder).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Callable

from hushtype import __version__

log = logging.getLogger(__name__)

REPO = "khurramiftikhar77/Hushtype"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
_ASSET = re.compile(r"^Hushtype-Setup-[\d.]+\.exe$", re.IGNORECASE)
_HEADERS = {"User-Agent": "Hushtype-updater", "Accept": "application/vnd.github+json"}


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def read_release(data: dict, current: str = __version__) -> dict:
    """Turns the GitHub API answer into what the Settings screen shows."""
    latest = (data.get("tag_name") or "").lstrip("vV")
    asset = next((a for a in data.get("assets", []) if _ASSET.match(a.get("name", ""))), None)
    return {
        "current": current,
        "latest": latest,
        "newer": bool(latest) and parse_version(latest) > parse_version(current),
        "notes": (data.get("body") or "").strip()[:2000],
        "page": data.get("html_url") or RELEASES_PAGE,
        "asset_url": asset["browser_download_url"] if asset else None,
        "asset_name": asset["name"] if asset else None,
        "size": int(asset["size"]) if asset else 0,
        "can_install": bool(asset) and getattr(sys, "frozen", False) and sys.platform == "win32",
    }


def check(timeout: float = 15) -> dict:
    req = urllib.request.Request(LATEST_URL, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https URL)
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"current": __version__, "latest": None, "newer": False, "page": RELEASES_PAGE,
                    "notes": "", "asset_url": None, "size": 0, "can_install": False}
        raise
    return read_release(data)


class Updater:
    """Downloads and starts the installer, reporting progress for the UI."""

    def __init__(self):
        self.state: dict = {"status": "idle"}  # idle | checking | ready | downloading | installing | error
        self.release: dict | None = None

    def check(self) -> dict:
        self.state = {"status": "checking"}
        try:
            self.release = check()
            self.state = {"status": "ready", **self.release}
        except Exception as e:
            log.exception("Update check failed")
            self.state = {"status": "error", "error": f"Could not reach GitHub: {e}"}
        return self.state

    def install(self, on_ready_to_quit: Callable[[], None]) -> None:
        rel = self.release
        if not rel or not rel.get("asset_url") or not rel.get("can_install"):
            self.state = {"status": "error", "error": "No installer available for this version."}
            return
        threading.Thread(target=self._download_and_run, args=(rel, on_ready_to_quit), daemon=True).start()

    def _download_and_run(self, rel: dict, on_ready_to_quit: Callable[[], None]) -> None:
        folder = Path(tempfile.gettempdir()) / "Hushtype-update"
        folder.mkdir(exist_ok=True)
        target = folder / rel["asset_name"]
        total = rel["size"]
        self.state = {"status": "downloading", "done": 0, "total": total, "latest": rel["latest"]}
        try:
            req = urllib.request.Request(rel["asset_url"], headers={"User-Agent": _HEADERS["User-Agent"]})
            with urllib.request.urlopen(req, timeout=60) as r, open(target, "wb") as f:  # noqa: S310
                done = 0
                while chunk := r.read(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    self.state["done"] = done
            if total and target.stat().st_size != total:
                raise IOError("The download was incomplete. Please try again.")
            self.state = {"status": "installing", "latest": rel["latest"]}
            run_installer(target)
            on_ready_to_quit()
        except Exception as e:
            log.exception("Update failed")
            self.state = {"status": "error", "error": str(e)}


def run_installer(path: Path) -> None:
    """Starts the installer a moment after Hushtype quits, without a console window."""
    args = f'"{path}" /SILENT /SP- /NOCANCEL /SUPPRESSMSGBOXES /NORESTART'
    cmd = f'cmd /c "ping -n 3 127.0.0.1 >nul & start "" {args}"'
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    subprocess.Popen(cmd, creationflags=flags, close_fds=True, shell=False)  # noqa: S603
