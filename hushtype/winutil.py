"""Small Windows helpers. Every function is a safe no-op on other systems."""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

IS_WIN = sys.platform == "win32"
APP_NAME = "Hushtype"
MUTEX_NAME = "HushtypeSingleInstance"  # also used by the installer to detect a running app
_IPC_PORT = 47821

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32


def foreground_window() -> tuple[int, str, str]:
    """(window handle, window title, exe name) of the app the user is typing in."""
    if not IS_WIN:
        return 0, "", ""
    hwnd = _user32.GetForegroundWindow()
    length = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    exe = ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        try:
            size = wintypes.DWORD(1024)
            path = ctypes.create_unicode_buffer(1024)
            if _kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                exe = Path(path.value).name
        finally:
            _kernel32.CloseHandle(handle)
    return hwnd, title, exe


_FRIENDLY = {
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "brave.exe": "Brave",
    "outlook.exe": "Outlook", "olk.exe": "Outlook", "winword.exe": "Word", "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint", "teams.exe": "Teams", "ms-teams.exe": "Teams", "slack.exe": "Slack",
    "whatsapp.exe": "WhatsApp", "notepad.exe": "Notepad", "code.exe": "VS Code",
}
_SITES = ["LinkedIn", "Gmail", "Outlook", "WhatsApp", "Slack", "Teams", "ChatGPT", "Claude", "Facebook"]


def friendly_app(title: str, exe: str) -> str:
    """'Chrome · LinkedIn' style label for history."""
    import re

    app = _FRIENDLY.get(exe.lower(), Path(exe).stem.capitalize() if exe else "")
    site = next((s for s in _SITES if re.search(r"\b" + s.lower() + r"\b", title.lower())), "")
    if site and site != app:
        return f"{app} · {site}" if app else site
    return app or (title[:40] if title else "")


def focus_window(hwnd: int) -> None:
    """Brings the original app back to the front before pasting, if focus moved."""
    if not IS_WIN or not hwnd:
        return
    try:
        if _user32.GetForegroundWindow() != hwnd:
            _user32.SetForegroundWindow(hwnd)
    except Exception:
        log.debug("Could not refocus window", exc_info=True)


# ---------- start with Windows ----------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command(background: bool = True) -> str:
    if getattr(sys, "frozen", False):
        cmd = f'"{sys.executable}"'
    else:
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        cmd = f'"{pythonw if pythonw.exists() else exe}" -m hushtype'
    return cmd + (" --background" if background else "")


def set_autostart(enabled: bool) -> None:
    if not IS_WIN:
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ---------- single instance ----------

class SingleInstance:
    """Ensures one Hushtype runs. A second launch asks the first to show its window."""

    def __init__(self):
        self._mutex = None
        self._server: socket.socket | None = None
        self.already_running = False
        if IS_WIN:
            self._mutex = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
            self.already_running = _kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        else:
            try:
                self._server = self._bind()
            except OSError:
                self.already_running = True

    @staticmethod
    def _bind() -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", _IPC_PORT))
        s.listen(1)
        return s

    def notify_running(self) -> None:
        try:
            with socket.create_connection(("127.0.0.1", _IPC_PORT), timeout=1) as c:
                c.sendall(b"show")
        except OSError:
            pass

    def listen(self, on_show: Callable[[], None]) -> None:
        """Calls on_show when another launch asks this one to come forward."""
        if self._server is None:
            try:
                self._server = self._bind()
            except OSError:
                log.warning("Could not open the local wake-up port")
                return

        def loop():
            while True:
                try:
                    conn, _ = self._server.accept()
                    with conn:
                        if conn.recv(16) == b"show":
                            on_show()
                except OSError:
                    return

        threading.Thread(target=loop, daemon=True).start()


def open_folder(path: Path) -> None:
    if IS_WIN:
        os.startfile(str(path))  # noqa: S606
