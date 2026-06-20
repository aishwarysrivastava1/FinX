"""
routes/auth.py — v2 authentication endpoints.

Mounted at /api/v2 in main.py, so full paths are:
  POST   /api/v2/auth/signup
  GET    /api/v2/auth/verify-email?token=...
  POST   /api/v2/auth/login
  POST   /api/v2/auth/refresh
  GET    /api/v2/auth/me
  GET    /api/v2/auth/google/login
  GET    /api/v2/auth/google/callback

Zero overlap with the existing /api/auth/* routes.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.config import settings
from core.db import get_db
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from models.user import User
from schemas.auth import (
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserOut,
)
from services.auth_service import (
    create_email_user,
    create_google_user,
    get_user_by_email,
    get_user_by_id,
    send_verification_email,
    verify_email_token,
)
from services.oauth_service import get_google_user_info, google_client

router = APIRouter(prefix="/auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v2/auth/login", auto_error=False)


# ── Simple in-memory rate limiter ────────────────────────────────────────────
# Tracks failed login attempts per IP: {ip: [timestamp, ...]}
_login_attempts: Dict[str, list] = defaultdict(list)
_RATE_WINDOW   = 60   # seconds
_MAX_ATTEMPTS  = 10   # per window


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    window_start = now - _RATE_WINDOW
    attempts = [t for t in _login_attempts[ip] if t > window_start]
    _login_attempts[ip] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {_RATE_WINDOW} seconds.",
        )


def _record_attempt(ip: str) -> None:
    _login_attempts[ip].append(time.time())


def _clear_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)


# ── Auth dependency ───────────────────────────────────────────────────────────

def get_current_v2_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token, expected_type="access")
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = get_user_by_id(db, payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


# ── POST /auth/signup ─────────────────────────────────────────────────────────

@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register with email + password",
)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    if get_user_by_email(db, req.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = create_email_user(db, req.email, req.password)
    result = send_verification_email(user.email, user.verification_token)

    return SignupResponse(
        registered=True,
        email_sent=result.get("sent", False),
        verification_link=result.get("verification_link"),
    )


# ── GET /auth/verify-email ────────────────────────────────────────────────────

@router.get(
    "/verify-email",
    summary="Verify email address via token from link",
)
def verify_email(token: str, db: Session = Depends(get_db)):
    user = verify_email_token(db, token)
    frontend_url = settings.APP_URL.rstrip("/")
    if not user:
        return RedirectResponse(url=f"{frontend_url}/?verified=error")
    return RedirectResponse(url=f"{frontend_url}/?verified=success")


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email + password",
)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    user = get_user_by_email(db, req.email)

    # Constant-time failure — never reveal whether email exists
    if not user or not user.hashed_password:
        _record_attempt(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not verify_password(req.password, user.hashed_password):
        _record_attempt(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    _clear_attempts(ip)

    access  = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id, user.email, user.refresh_token_version)
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── POST /auth/refresh ────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate tokens using a valid refresh token",
)
def refresh_tokens(req: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(req.refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    user = get_user_by_id(db, payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    # Version check — invalidates all older refresh tokens after logout/rotation
    if payload.get("version", 0) != user.refresh_token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked.",
        )

    # Rotate: bump version so the old token can't be reused
    user.refresh_token_version += 1
    db.commit()

    access  = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id, user.email, user.refresh_token_version)
    return TokenResponse(access_token=access, refresh_token=refresh)


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the currently authenticated user",
)
def me(current_user: User = Depends(get_current_v2_user)):
    return current_user


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google/login", summary="Redirect to Google login")
async def google_login(request: Request):
    client = google_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server.",
        )
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", summary="Google OAuth callback — returns JWT tokens")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    client = google_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server.",
        )

    user_info = await get_google_user_info(request)
    if not user_info or not user_info.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to retrieve email from Google. Please try again.",
        )

    email = user_info["email"].strip().lower()
    name  = (user_info.get("name") or user_info.get("given_name") or "").strip() or None
    user  = get_user_by_email(db, email)

    if user is None:
        # First-time Google login → create pre-verified account
        user = create_google_user(db, email, name=name)
    else:
        # Update name if Google provides one and we don't have it yet
        if name and not user.name:
            user.name = name
            db.commit()

    access  = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id, user.email, user.refresh_token_version)

    # Redirect to frontend with tokens in URL fragment (SPA-friendly)
    frontend_url = settings.APP_URL.rstrip("/")
    redirect_url = (
        f"{frontend_url}/?"
        f"access_token={access}&refresh_token={refresh}&auth=google"
    )
    return RedirectResponse(url=redirect_url)
