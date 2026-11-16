"""Local SQLite database: projects, their app rules, and dictation history."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hushtype.paths import db_path

INBOX_ID = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT 'teal',
    language TEXT NOT NULL DEFAULT 'en',      -- 'en' or 'ur'
    remove_fillers INTEGER NOT NULL DEFAULT 1,
    capitalize INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL                     -- matched against app name and window title
);
CREATE TABLE IF NOT EXISTS dictations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,                 -- ISO 8601, UTC
    language TEXT NOT NULL,
    duration REAL NOT NULL,                   -- seconds of audio recorded
    process_time REAL NOT NULL,               -- seconds spent transcribing
    text TEXT NOT NULL,                       -- final text that was pasted
    raw_text TEXT NOT NULL,                   -- model output before cleanup
    app TEXT                                  -- where it was pasted
);
CREATE INDEX IF NOT EXISTS idx_dict_created ON dictations(created_at);
CREATE INDEX IF NOT EXISTS idx_dict_project ON dictations(project_id);
"""

COLORS = ["teal", "indigo", "orange", "pink", "sky", "lime"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class Store:
    def __init__(self, path: Path | str | None = None):
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path or db_path()), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self.version = 0  # bumps on every change so the UI knows to refresh
        with self._lock:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.executescript(SCHEMA)
            if not self._db.execute("SELECT 1 FROM projects WHERE id = ?", (INBOX_ID,)).fetchone():
                self._db.execute(
                    "INSERT INTO projects (id, name, color, language, created_at) VALUES (?, 'Inbox', 'teal', 'en', ?)",
                    (INBOX_ID, _now()),
                )
            self._db.commit()

    def _changed(self) -> None:
        self._db.commit()
        self.version += 1

    # ---------- projects ----------

    def projects(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT p.*, (SELECT COUNT(*) FROM dictations d WHERE d.project_id = p.id) AS count"
                " FROM projects p ORDER BY p.id = 1 DESC, p.name COLLATE NOCASE"
            ).fetchall()
            out = []
            for r in rows:
                p = dict(r)
                p["remove_fillers"] = bool(p["remove_fillers"])
                p["capitalize"] = bool(p["capitalize"])
                p["rules"] = [x[0] for x in self._db.execute(
                    "SELECT pattern FROM rules WHERE project_id = ? ORDER BY id", (p["id"],))]
                out.append(p)
            return out

    def project(self, project_id: int) -> dict | None:
        for p in self.projects():
            if p["id"] == project_id:
                return p
        return None

    def create_project(self, name: str, language: str = "en", color: str | None = None,
                       remove_fillers: bool = True, capitalize: bool = True,
                       rules: list[str] | None = None) -> dict:
        name = name.strip() or "Untitled"
        with self._lock:
            if color is None:
                n = self._db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
                color = COLORS[n % len(COLORS)]
            cur = self._db.execute(
                "INSERT INTO projects (name, color, language, remove_fillers, capitalize, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (name, color, language, int(remove_fillers), int(capitalize), _now()),
            )
            pid = cur.lastrowid
            self._set_rules(pid, rules or [])
            self._changed()
        return self.project(pid)

    def update_project(self, project_id: int, **fields) -> dict | None:
        allowed = {"name", "color", "language", "remove_fillers", "capitalize"}
        sets, args = [], []
        for k, v in fields.items():
            if k in allowed:
                if isinstance(v, bool):
                    v = int(v)
                if k == "name":
                    v = str(v).strip() or "Untitled"
                sets.append(f"{k} = ?")
                args.append(v)
        with self._lock:
            if sets:
                self._db.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", (*args, project_id))
            if "rules" in fields:
                self._set_rules(project_id, fields["rules"])
            self._changed()
        return self.project(project_id)

    def _set_rules(self, project_id: int, rules: list[str]) -> None:
        self._db.execute("DELETE FROM rules WHERE project_id = ?", (project_id,))
        for pattern in rules:
            pattern = str(pattern).strip().lower()
            if pattern:
                self._db.execute("INSERT INTO rules (project_id, pattern) VALUES (?, ?)", (project_id, pattern))

    def delete_project(self, project_id: int) -> None:
        """Deletes a project; its dictations move to the Inbox."""
        if project_id == INBOX_ID:
            raise ValueError("The Inbox cannot be deleted")
        with self._lock:
            self._db.execute("UPDATE dictations SET project_id = ? WHERE project_id = ?", (INBOX_ID, project_id))
            self._db.execute("DELETE FROM rules WHERE project_id = ?", (project_id,))
            self._db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            self._changed()

    def match_rule(self, app_text: str) -> int | None:
        """Returns the project whose rule appears in the app name or window title."""
        text = (app_text or "").lower()
        if not text:
            return None
        with self._lock:
            rows = self._db.execute(
                "SELECT r.project_id, r.pattern FROM rules r JOIN projects p ON p.id = r.project_id"
                " ORDER BY LENGTH(r.pattern) DESC"
            ).fetchall()
        for pid, pattern in rows:
            if pattern and pattern in text:
                return pid
        return None

    # ---------- dictations ----------

    def add(self, *, project_id: int, language: str, duration: float, process_time: float,
            text: str, raw_text: str, app: str | None = None, created_at: str | None = None) -> dict:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO dictations (project_id, created_at, language, duration, process_time, text, raw_text, app)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, created_at or _now(), language, duration, process_time, text, raw_text, app),
            )
            row = self._db.execute("SELECT * FROM dictations WHERE id = ?", (cur.lastrowid,)).fetchone()
            self._changed()
        return dict(row)

    def dictations(self, *, query: str = "", project_id: int | None = None,
                   language: str | None = None, limit: int = 300, oldest_first: bool = False) -> list[dict]:
        where, args = [], []
        if query:
            where.append("text LIKE ?")
            args.append(f"%{query}%")
        if project_id:
            where.append("project_id = ?")
            args.append(project_id)
        if language:
            where.append("language = ?")
            args.append(language)
        sql = "SELECT * FROM dictations"
        if where:
            sql += " WHERE " + " AND ".join(where)
        order = "ASC" if oldest_first else "DESC"
        sql += f" ORDER BY created_at {order}, id {order} LIMIT ?"
        args.append(limit)
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def last(self) -> dict | None:
        rows = self.dictations(limit=1)
        return rows[0] if rows else None

    def move(self, item_id: int, project_id: int) -> None:
        with self._lock:
            self._db.execute("UPDATE dictations SET project_id = ? WHERE id = ?", (project_id, item_id))
            self._changed()

    def delete(self, item_id: int) -> None:
        with self._lock:
            self._db.execute("DELETE FROM dictations WHERE id = ?", (item_id,))
            self._changed()

    def clear(self) -> int:
        with self._lock:
            n = self._db.execute("DELETE FROM dictations").rowcount
            self._changed()
        return n

    def count_older_than(self, days: int) -> int:
        with self._lock:
            return self._db.execute(
                "SELECT COUNT(*) FROM dictations WHERE created_at < ?", (_cutoff(days),)).fetchone()[0]

    def delete_older_than(self, days: int) -> int:
        with self._lock:
            n = self._db.execute("DELETE FROM dictations WHERE created_at < ?", (_cutoff(days),)).rowcount
            self._changed()
        return n

    def stats(self) -> dict:
        today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        week = today - timedelta(days=today.weekday())
        with self._lock:
            today_n = self._db.execute(
                "SELECT COUNT(*) FROM dictations WHERE created_at >= ?",
                (today.astimezone(timezone.utc).isoformat(),)).fetchone()[0]
            rows = self._db.execute(
                "SELECT text, duration, process_time FROM dictations WHERE created_at >= ?",
                (week.astimezone(timezone.utc).isoformat(),)).fetchall()
            total = self._db.execute("SELECT COUNT(*) FROM dictations").fetchone()[0]
            recent_wait = [r[0] for r in self._db.execute(
                "SELECT process_time FROM dictations ORDER BY id DESC LIMIT 20")]
        words = sum(len(r[0].split()) for r in rows)
        seconds = sum(r[1] for r in rows)
        avg_wait = sum(recent_wait) / len(recent_wait) if recent_wait else None
        return {"today": today_n, "week_words": words, "week_seconds": seconds,
                "total": total, "avg_wait": avg_wait}

    def close(self) -> None:
        with self._lock:
            self._db.close()
