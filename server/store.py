"""Persistence for chats, messages, and the per-user profile — via SQLAlchemy.

All chat/message access is scoped by user_id (multi-tenant). Backed by Postgres in
production or SQLite in dev (see db/base.py).
"""
from __future__ import annotations

import json
import time

from sqlalchemy import func, select

from db.base import init_db as _init_db, session_scope
from db.models import Chat, Message, User


def init_db() -> None:
    _init_db()


# ------------------------------------------------------------------ chats
def create_chat(user_id: str, title: str = "New chat") -> dict:
    with session_scope() as s:
        chat = Chat(user_id=user_id, title=title)
        s.add(chat)
        s.flush()
        return {"id": chat.id, "title": chat.title,
                "created_at": chat.created_at, "updated_at": chat.updated_at}


def list_chats(user_id: str) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Chat, func.count(Message.id))
            .outerjoin(Message, Message.chat_id == Chat.id)
            .where(Chat.user_id == user_id)
            .group_by(Chat.id)
            .order_by(Chat.updated_at.desc())
        ).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at,
             "updated_at": c.updated_at, "n": n} for c, n in rows]


def get_chat(chat_id: str, user_id: str | None = None) -> dict | None:
    with session_scope() as s:
        c = s.get(Chat, chat_id)
        if not c or (user_id is not None and c.user_id != user_id):
            return None
        return {"id": c.id, "title": c.title, "created_at": c.created_at,
                "updated_at": c.updated_at, "summary": c.summary,
                "unsummarized_start": c.unsummarized_start, "user_id": c.user_id}


def rename_chat(chat_id: str, title: str) -> None:
    with session_scope() as s:
        c = s.get(Chat, chat_id)
        if c:
            c.title = title[:200]


def delete_chat(chat_id: str, user_id: str | None = None) -> None:
    with session_scope() as s:
        c = s.get(Chat, chat_id)
        if not c or (user_id is not None and c.user_id != user_id):
            return
        s.query(Message).filter(Message.chat_id == chat_id).delete()
        s.delete(c)


def update_summary(chat_id: str, summary: str, unsummarized_start: int) -> None:
    with session_scope() as s:
        c = s.get(Chat, chat_id)
        if c:
            c.summary = summary
            c.unsummarized_start = unsummarized_start


# ------------------------------------------------------------------ messages
def add_message(chat_id: str, role: str, content: str,
                sources: list | None = None, trace: dict | None = None) -> int:
    with session_scope() as s:
        m = Message(chat_id=chat_id, role=role, content=content,
                    sources=json.dumps(sources or []), trace=json.dumps(trace or {}))
        s.add(m)
        c = s.get(Chat, chat_id)
        if c:
            c.updated_at = time.time()
        s.flush()
        return m.id


def get_messages(chat_id: str) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.id)
        ).scalars().all()
        return [{"role": m.role, "content": m.content,
                 "sources": json.loads(m.sources), "trace": json.loads(m.trace),
                 "created_at": m.created_at} for m in rows]


# ------------------------------------------------------------------ per-user profile
def get_user_profile(user_id: str) -> str:
    with session_scope() as s:
        u = s.get(User, user_id)
        return u.profile if u else ""


def set_user_profile(user_id: str, profile: str) -> None:
    with session_scope() as s:
        u = s.get(User, user_id)
        if u:
            u.profile = profile
