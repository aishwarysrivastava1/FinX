"""
services/oauth_service.py — Google OAuth 2.0 via Authlib.

Lazy-initialised: if GOOGLE_CLIENT_ID is blank the `oauth` object
is None and the routes return 503 gracefully.
"""
from __future__ import annotations

from typing import Optional

from core.config import settings

oauth = None  # type: ignore[assignment]

if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
    try:
        from authlib.integrations.starlette_client import OAuth
        from starlette.config import Config as _StarletteConfig

        _sc = _StarletteConfig(
            environ={
                "GOOGLE_CLIENT_ID": settings.GOOGLE_CLIENT_ID,
                "GOOGLE_CLIENT_SECRET": settings.GOOGLE_CLIENT_SECRET,
            }
        )
        oauth = OAuth(_sc)
        oauth.register(
            name="google",
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )
        print("[Auth v2] Google OAuth configured")
    except ImportError:
        print("[Auth v2] authlib not installed — Google OAuth disabled")
else:
    print("[Auth v2] GOOGLE_CLIENT_ID not set — Google OAuth disabled")


def google_client():
    """Returns the registered Google OAuth client or None."""
    if oauth is None:
        return None
    return oauth.google  # type: ignore[attr-defined]


async def get_google_user_info(request) -> Optional[dict]:
    """
    Called inside the OAuth callback handler.
    Returns {'email': ..., 'name': ..., 'sub': ...} or None on failure.
    """
    client = google_client()
    if client is None:
        return None
    try:
        token = await client.authorize_access_token(request)
        user_info = token.get("userinfo") or await client.userinfo(token=token)
        return dict(user_info)
    except Exception as exc:
        print(f"[Auth v2] Google userinfo error: {exc}")
        return None
