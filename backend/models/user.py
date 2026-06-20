"""
models/user.py — SQLAlchemy ORM model for auth_users table.

Uses String(36) for the UUID primary key so it works on both
SQLite (no native UUID) and PostgreSQL without a custom type.
Table name is `auth_users` — completely separate from the existing `users` table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from core.db import Base


def _now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "auth_users"

    # ── Identity ─────────────────────────────────────────────
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    email = Column(String(254), unique=True, nullable=False, index=True)
    # Display name — populated from Google userinfo; null for email/password accounts
    name  = Column(String(255), nullable=True)

    # ── Credentials ──────────────────────────────────────────
    # Nullable: Google-only accounts never have a password
    hashed_password = Column(String(255), nullable=True)

    # ── Verification ─────────────────────────────────────────
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(100), nullable=True)
    verification_expires_at = Column(DateTime(timezone=True), nullable=True)

    # ── Google OAuth ─────────────────────────────────────────
    is_google_account = Column(Boolean, default=False, nullable=False)

    # ── Token rotation ───────────────────────────────────────
    refresh_token_version = Column(Integer, default=0, nullable=False)

    # ── Audit ────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True),
        default=_now_utc,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r} verified={self.is_verified}>"
