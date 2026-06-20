"""
core/db.py — SQLAlchemy engine + session for the v2 auth module.

Completely separate from the existing database.py (raw sqlite3).
Supports:
  - SQLite  (default, zero-config)
  - PostgreSQL  (set DATABASE_URL=postgresql+psycopg2://... in .env)
"""
from __future__ import annotations

import re

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
try:
    # SQLAlchemy 2.x
    from sqlalchemy.orm import DeclarativeBase
except ImportError:
    # SQLAlchemy 1.4 fallback
    from sqlalchemy.ext.declarative import declarative_base

from core.config import settings

_url = settings.DATABASE_URL

# Normalize a bare file path (e.g. "data/finx.db") to a proper SQLite URL.
# The legacy database.py uses DATABASE_URL as a raw path; SQLAlchemy needs a full URL.
if _url and "://" not in _url:
    _url = f"sqlite:///{_url}"

# SQLAlchemy requires postgresql:// not the legacy postgres:// scheme
_url = re.sub(r"^postgres://", "postgresql://", _url)

if _url.startswith("sqlite"):
    _engine_kwargs = {"connect_args": {"check_same_thread": False}}
else:
    _engine_kwargs = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}

engine = create_engine(_url, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if "DeclarativeBase" in globals():
    class Base(DeclarativeBase):
        pass
else:
    Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a SQLAlchemy session, closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_auth_db() -> None:
    """Creates all v2 auth tables (idempotent — safe to call on every startup)."""
    from models.user import User  # noqa: F401 — registers the model with Base
    Base.metadata.create_all(bind=engine)
    # Migrate existing auth_users table: add name column if missing
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE auth_users ADD COLUMN name VARCHAR(255)"))
            conn.commit()
            print("[Auth v2] Migrated: added name column")
        except Exception:
            pass  # Column already exists — safe to ignore
    print("[Auth v2] DB tables ready")
