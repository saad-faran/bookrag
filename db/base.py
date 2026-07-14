"""SQLAlchemy engine + session, driven by DATABASE_URL.

- Production/Docker:  postgresql+psycopg2://bookrag:bookrag@localhost:5432/bookrag
- Local dev (default): sqlite file — zero setup, same models & migrations.

pgvector (Phase 2, project-document embeddings) requires Postgres; auth + chats work
on either backend.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'bookrag.db'}")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create tables if absent (dev bootstrap; Alembic manages real migrations)."""
    from db import models  # noqa: F401  (register mappers)
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql")
