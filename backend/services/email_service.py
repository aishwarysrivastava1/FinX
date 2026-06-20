from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_verification_email(to_email: str, token: str) -> dict:
    app_url = os.getenv("APP_URL", "http://localhost:5173").rstrip("/")
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "").strip()

    # Primary verification endpoint is backend API; frontend link is kept as a fallback.
    api_verify_link = f"{backend_url}/api/auth/verify/{token}"
    frontend_verify_link = f"{app_url}/?verify={token}"
    link = api_verify_link

    if not smtp_user or not smtp_pass:
        # Dev fallback: print the link so you can verify without SMTP
        print(f"[EMAIL] SMTP not configured — verify link: {api_verify_link}")
        return {
            "sent": False,
            "reason": "smtp_not_configured",
            "verification_link": api_verify_link,
        }

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your FIN-X account"
    msg["From"]    = smtp_user
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#2563eb">Welcome to FIN-X</h2>
      <p>Click the button below to verify your email address. The link expires in <strong>24 hours</strong>.</p>
      <a href="{link}"
         style="display:inline-block;padding:10px 24px;background:#2563eb;color:#fff;
                border-radius:8px;text-decoration:none;font-weight:600">
        Verify my account
      </a>
      <p style="margin-top:16px;font-size:12px;color:#6b7280">
        Or copy this URL into your browser:<br>{link}
      </p>
      <p style="margin-top:8px;font-size:12px;color:#6b7280">
        Frontend fallback link:<br>{frontend_verify_link}
      </p>
    </div>
    """
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())
    return {"sent": True, "reason": None, "verification_link": None}
