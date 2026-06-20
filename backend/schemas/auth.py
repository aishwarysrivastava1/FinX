"""
schemas/auth.py — Pydantic request/response models for v2 auth endpoints.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator


# ── Requests ─────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if len(v) > 254:
            raise ValueError("Email address is too long")
        if not re.match(
            r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$",
            v,
        ):
            raise ValueError("Invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must include at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must include at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must include at least one digit")
        if not re.search(r"[^\w\s]", v):
            raise ValueError("Password must include at least one special character (!@#$…)")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return (v or "").strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Responses ────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SignupResponse(BaseModel):
    registered: bool
    email_sent: bool
    # Only populated when SMTP is not configured (dev mode)
    verification_link: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    is_verified: bool
    is_google_account: bool

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
