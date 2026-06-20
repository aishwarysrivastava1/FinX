"""
core/config.py — centralised settings for the v2 auth module.
Reads from environment / .env automatically via pydantic-settings.
All other modules import `settings` from here.
"""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./data/finx.db"

    # ── JWT ──────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "dev-secret-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # ── SMTP ─────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""

    # ── URLs ─────────────────────────────────────────────────
    # Defaults for local dev — Render ENV will override these
    APP_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"

    # ── Google OAuth ─────────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # MUST match Google Console + Render env
    GOOGLE_REDIRECT_URI: str = "https://fin-x-backend-diib.onrender.com/api/v2/auth/google/callback"


settings = Settings()