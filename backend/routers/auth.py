from __future__ import annotations

import secrets
import re
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, field_validator
from typing import Dict, Any

from database import db_fetchone, db_execute
from services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_user_id_from_token,
)
from services.email_service import send_verification_email


router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class RegisterRequest(BaseModel):
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 8 or len(v) > 128:
            raise ValueError("password must be 8-128 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must include at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("password must include at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must include at least one number")
        if not re.search(r"[^\w\s]", v):
            raise ValueError("password must include at least one special character")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if len(v) > 254:
            raise ValueError("invalid email")
        if not re.match(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$", v):
            raise ValueError("invalid email")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if len(v) > 254:
            raise ValueError("invalid email")
        if not re.match(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$", v):
            raise ValueError("invalid email")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    user_id = get_user_id_from_token(token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db_fetchone("SELECT id, email FROM users WHERE id=?", (user_id,))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest):
    existing = db_fetchone("SELECT id FROM users WHERE email=?", (req.email.lower(),))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    password_hash = hash_password(req.password)
    verification_token = secrets.token_urlsafe(32)
    verification_expires_at = (dt.datetime.utcnow() + dt.timedelta(hours=24)).isoformat()
    db_execute(
        "INSERT INTO users (email, password_hash, is_verified, verification_token, verification_expires_at, refresh_token_version) VALUES (?,?,0,?,?,0)",
        (req.email.lower(), password_hash, verification_token, verification_expires_at),
    )
    email_sent = False
    verify_link = None
    email_reason = None
    try:
        email_result = send_verification_email(req.email.lower(), verification_token)
        email_sent = bool(email_result.get("sent"))
        verify_link = email_result.get("verification_link")
        email_reason = email_result.get("reason")
    except Exception as e:
        email_reason = "smtp_send_failed"
        print(f"[AUTH] Failed to send verification email: {e}")

    return {
        "success": True,
        "data": {
            "registered": True,
            "check_email": True,
            "email_sent": email_sent,
            "email_reason": email_reason,
            # Expose fallback link only when SMTP delivery is unavailable.
            "verification_link": verify_link if not email_sent else None,
        },
        "error": None,
    }


@router.get("/auth/verify/{token}")
def verify_email(token: str):
    user = db_fetchone(
        "SELECT id, verification_expires_at FROM users WHERE verification_token=?",
        (token,),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link")

    expiry = user.get("verification_expires_at")
    if expiry:
        try:
            expiry_dt = dt.datetime.fromisoformat(str(expiry))
            if expiry_dt < dt.datetime.utcnow():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification link expired")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification link")

    db_execute(
        "UPDATE users SET is_verified=1, verification_token=NULL, verification_expires_at=NULL WHERE id=?",
        (user["id"],),
    )
    return {"success": True, "data": {"verified": True}, "error": None}


@router.post("/auth/login")
def login(req: LoginRequest):
    user = db_fetchone(
        "SELECT id, email, password_hash, is_verified, refresh_token_version FROM users WHERE email=?",
        (req.email.lower(),),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(req.password, user.get("password_hash") or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.get("is_verified"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in")

    user_id = int(user["id"])
    email = str(user["email"])
    token_version = int(user.get("refresh_token_version") or 0)
    access_token = create_access_token(user_id=user_id, email=email)
    refresh_token = create_refresh_token(user_id=user_id, email=email, token_version=token_version)
    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
        "error": None,
    }


@router.post("/auth/refresh")
def refresh_tokens(req: RefreshRequest):
    payload = verify_token(req.refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db_fetchone(
        "SELECT id, email, is_verified, refresh_token_version FROM users WHERE id=?",
        (int(sub),),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.get("is_verified"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email is not verified")

    token_version = int(user.get("refresh_token_version") or 0)
    incoming_version = int(payload.get("token_version") or -1)
    if incoming_version != token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    # Rotate refresh token by bumping version so old refresh token can no longer be reused.
    new_version = token_version + 1
    db_execute("UPDATE users SET refresh_token_version=? WHERE id=?", (new_version, int(user["id"])))

    new_access_token = create_access_token(user_id=int(user["id"]), email=str(user["email"]))
    new_refresh_token = create_refresh_token(
        user_id=int(user["id"]), email=str(user["email"]), token_version=new_version
    )

    return {
        "success": True,
        "data": {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        },
        "error": None,
    }


@router.get("/auth/me")
def me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"success": True, "data": user, "error": None}

