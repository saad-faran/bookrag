"""SQLite persistence for chats, messages, and the cross-chat user profile.

Deliberately dependency-free (stdlib sqlite3). One small DB file next to the code.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "bookrag.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New chat',
                created_at REAL, updated_at REAL,
                summary TEXT NOT NULL DEFAULT '',
                unsummarized_start INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                trace TEXT NOT NULL DEFAULT '{}',
                created_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                profile TEXT NOT NULL DEFAULT '',
                updated_at REAL
            );
            INSERT OR IGNORE INTO user_profile (id, profile, updated_at) VALUES (1, '', 0);
            """
        )


# ------------------------------------------------------------------ chats
def create_chat(title: str = "New chat") -> dict:
    cid = uuid.uuid4().hex[:12]
    now = time.time()
    with _conn() as c:
        c.execute("INSERT INTO chats (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                  (cid, title, now, now))
    return {"id": cid, "title": title, "created_at": now, "updated_at": now}


def list_chats() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, title, created_at, updated_at, "
            "(SELECT COUNT(*) FROM messages m WHERE m.chat_id = chats.id) AS n "
            "FROM chats ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_chat(chat_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


def rename_chat(chat_id: str, title: str) -> None:
    with _conn() as c:
        c.execute("UPDATE chats SET title = ? WHERE id = ?", (title[:80], chat_id))


def delete_chat(chat_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        c.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def touch_chat(chat_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (time.time(), chat_id))


def update_summary(chat_id: str, summary: str, unsummarized_start: int) -> None:
    with _conn() as c:
        c.execute("UPDATE chats SET summary = ?, unsummarized_start = ? WHERE id = ?",
                  (summary, unsummarized_start, chat_id))


# ------------------------------------------------------------------ messages
def add_message(chat_id: str, role: str, content: str,
                sources: list | None = None, trace: dict | None = None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO messages (chat_id, role, content, sources, trace, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (chat_id, role, content, json.dumps(sources or []), json.dumps(trace or {}), time.time()),
        )
        c.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (time.time(), chat_id))
        return cur.lastrowid


def get_messages(chat_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content, sources, trace, created_at FROM messages "
            "WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["sources"] = json.loads(d["sources"])
        d["trace"] = json.loads(d["trace"])
        out.append(d)
    return out


# ------------------------------------------------------------------ user profile
def get_user_profile() -> str:
    with _conn() as c:
        row = c.execute("SELECT profile FROM user_profile WHERE id = 1").fetchone()
    return row["profile"] if row else ""


def set_user_profile(profile: str) -> None:
    with _conn() as c:
        c.execute("UPDATE user_profile SET profile = ?, updated_at = ? WHERE id = 1",
                  (profile, time.time()))
