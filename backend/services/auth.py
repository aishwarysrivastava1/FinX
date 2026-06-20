from __future__ import annotations

import os
import datetime as dt
import secrets
from typing import Optional, Any

import bcrypt
from jose import jwt, JWTError

def _get_secret() -> str:
    jwt_secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not jwt_secret:
        return "dev-secret-change-me"
    return jwt_secret


def _get_alg() -> str:
    return os.getenv("JWT_ALG", "HS256").strip()


def _get_access_expiry_minutes() -> int:
    return int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


def _get_refresh_expiry_days() -> int:
    return int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "14"))


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int, email: str) -> str:
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(minutes=_get_access_expiry_minutes())
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "jti": secrets.token_urlsafe(18),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_get_alg())


def create_refresh_token(user_id: int, email: str, token_version: int) -> str:
    now = dt.datetime.utcnow()
    exp = now + dt.timedelta(days=_get_refresh_expiry_days())
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "refresh",
        "token_version": int(token_version),
        "jti": secrets.token_urlsafe(24),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_get_alg())


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _get_secret(), algorithms=[_get_alg()])


def verify_token(token: str, expected_type: str) -> dict[str, Any] | None:
    try:
        payload = decode_access_token(token)
        if payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


def get_user_id_from_token(token: str) -> Optional[int]:
    payload = verify_token(token, expected_type="access")
    if not payload:
        return None
    sub = payload.get("sub")
    return int(sub) if sub is not None else None

