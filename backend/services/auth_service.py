"""
services/auth_service.py — business logic for v2 auth.
DB operations, email dispatch, user creation/lookup.
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session

from core.config import settings
from core.security import generate_opaque_token, hash_password
from models.user import User


# ── User queries ─────────────────────────────────────────────────────────────

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower()).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


# ── User creation ────────────────────────────────────────────────────────────

def create_email_user(db: Session, email: str, password: str) -> User:
    """Creates an unverified email/password user and returns it."""
    token = generate_opaque_token(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        is_verified=False,
        is_google_account=False,
        verification_token=token,
        verification_expires_at=expires_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_google_user(db: Session, email: str, name: Optional[str] = None) -> User:
    """Creates a pre-verified Google OAuth user."""
    user = User(
        email=email.lower(),
        name=name,
        hashed_password=None,
        is_verified=True,
        is_google_account=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Email verification ───────────────────────────────────────────────────────

def verify_email_token(db: Session, token: str) -> Optional[User]:
    """
    Looks up the token, checks expiry, marks user as verified.
    Returns the User on success, None on failure.
    """
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        return None

    if user.verification_expires_at:
        exp = user.verification_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return None  # expired

    user.is_verified = True
    user.verification_token = None
    user.verification_expires_at = None
    db.commit()
    db.refresh(user)
    return user


# ── Email sending ────────────────────────────────────────────────────────────

def send_verification_email(to_email: str, token: str) -> dict:
    """
    Sends a verification email via SMTP.

    Returns:
        {"sent": True}  — email delivered
        {"sent": False, "verification_link": str}  — SMTP not configured (dev mode)
    """
    link = f"{settings.BACKEND_URL.rstrip('/')}/api/v2/auth/verify-email?token={token}"

    if not settings.SMTP_USER or not settings.SMTP_PASS:
        print(f"[Auth v2] SMTP not configured — dev verify link: {link}")
        return {"sent": False, "verification_link": link}

    html = _build_email_html(link)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your Fin-X account"
    sender = settings.SMTP_FROM or settings.SMTP_USER
    msg["From"] = f"Fin-X <{sender}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.sendmail(settings.SMTP_USER, [to_email], msg.as_string())
        return {"sent": True}
    except Exception as exc:
        print(f"[Auth v2] SMTP error: {exc}")
        return {"sent": False, "verification_link": link}


def _build_email_html(link: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#f9fafb;padding:40px 16px">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;
                    border:1px solid #e5e7eb;overflow:hidden;max-width:480px">
        <!-- gradient strip -->
        <tr><td height="4"
                style="background:linear-gradient(90deg,#2563eb,#7c3aed);
                       font-size:0;line-height:0">&nbsp;</td></tr>
        <!-- body -->
        <tr><td style="padding:40px 36px">
          <!-- logo -->
          <table cellpadding="0" cellspacing="0" style="margin-bottom:28px">
            <tr>
              <td style="background:linear-gradient(135deg,#2563eb,#7c3aed);
                          border-radius:12px;width:40px;height:40px;
                          text-align:center;vertical-align:middle">
                <span style="color:#fff;font-size:13px;font-weight:900">FX</span>
              </td>
              <td style="padding-left:10px;vertical-align:middle">
                <span style="font-size:18px;font-weight:800;color:#111827">Fin-X</span>
                <span style="font-size:11px;color:#9ca3af;margin-left:6px">NSE Intelligence</span>
              </td>
            </tr>
          </table>
          <h1 style="margin:0 0 8px;font-size:24px;font-weight:800;color:#111827">
            Verify your email
          </h1>
          <p style="margin:0 0 24px;font-size:15px;color:#6b7280;line-height:1.6">
            Thanks for signing up! Click the button below to activate your account.
            This link expires in <strong style="color:#374151">24 hours</strong>.
          </p>
          <!-- CTA -->
          <table cellpadding="0" cellspacing="0" style="margin-bottom:28px">
            <tr>
              <td style="border-radius:12px;
                          background:linear-gradient(135deg,#2563eb,#7c3aed)">
                <a href="{link}"
                   style="display:inline-block;padding:14px 32px;color:#fff;
                          text-decoration:none;font-size:15px;font-weight:700;
                          border-radius:12px">
                  Verify my account &rarr;
                </a>
              </td>
            </tr>
          </table>
          <p style="margin:0 0 6px;font-size:12px;color:#9ca3af">
            Or copy this link:
          </p>
          <p style="margin:0;font-size:11px;color:#2563eb;word-break:break-all;
                     background:#eff6ff;border:1px solid #dbeafe;border-radius:8px;
                     padding:10px 12px;font-family:monospace">
            {link}
          </p>
        </td></tr>
        <!-- footer -->
        <tr><td style="padding:20px 36px;border-top:1px solid #f3f4f6;
                        font-size:11px;color:#d1d5db;text-align:center">
          Fin-X &middot; NSE Market Intelligence &middot; Educational use only
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
