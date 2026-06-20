"""
tests/test_auth.py — pytest suite for all v2 auth endpoints.

Uses an in-memory SQLite database so tests are fast and fully isolated.
Run with:  pytest tests/test_auth.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.db import Base, get_db
from main import app

# ── In-memory test DB ────────────────────────────────────────────────────────
# StaticPool ensures all sessions share ONE connection so the in-memory DB
# persists across requests during a test run.

TEST_DB_URL = "sqlite:///:memory:"
_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    from models.user import User  # noqa: F401 — register model with Base
    Base.metadata.create_all(bind=_engine)
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    Base.metadata.drop_all(bind=_engine)
    app.dependency_overrides.clear()


# ── Helpers ──────────────────────────────────────────────────────────────────

VALID_EMAIL    = "testuser@example.com"
VALID_PASSWORD = "Test@1234"

def _signup(client, email=VALID_EMAIL, password=VALID_PASSWORD):
    return client.post("/api/v2/auth/signup", json={"email": email, "password": password})

def _verify_user(email=VALID_EMAIL):
    """Directly mark user as verified in the test DB."""
    db = _Session()
    from models.user import User
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.is_verified = True
        db.commit()
    db.close()

def _login(client, email=VALID_EMAIL, password=VALID_PASSWORD):
    return client.post("/api/v2/auth/login", json={"email": email, "password": password})


# ── Signup tests ─────────────────────────────────────────────────────────────

class TestSignup:
    def test_success(self, client):
        res = _signup(client)
        assert res.status_code == 201
        body = res.json()
        assert body["registered"] is True
        assert "email_sent" in body

    def test_duplicate_email(self, client):
        res = _signup(client)
        assert res.status_code == 409
        assert "already exists" in res.json()["detail"]

    def test_invalid_email(self, client):
        res = _signup(client, email="not-an-email")
        assert res.status_code == 422

    def test_weak_password_too_short(self, client):
        res = _signup(client, email="new@example.com", password="Ab1!")
        assert res.status_code == 422

    def test_weak_password_no_uppercase(self, client):
        res = _signup(client, email="new@example.com", password="test@1234")
        assert res.status_code == 422

    def test_weak_password_no_digit(self, client):
        res = _signup(client, email="new@example.com", password="Test@abcd")
        assert res.status_code == 422

    def test_weak_password_no_special(self, client):
        res = _signup(client, email="new@example.com", password="Test12345")
        assert res.status_code == 422


# ── Login tests ───────────────────────────────────────────────────────────────

class TestLogin:
    def test_login_unverified_blocked(self, client):
        res = _login(client)
        assert res.status_code == 403
        assert "verify" in res.json()["detail"].lower()

    def test_login_success_after_verify(self, client):
        _verify_user()
        res = _login(client)
        assert res.status_code == 200
        body = res.json()
        assert "access_token"  in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        res = _login(client, password="WrongPass@99")
        assert res.status_code == 401

    def test_login_unknown_email(self, client):
        res = _login(client, email="ghost@example.com")
        assert res.status_code == 401

    def test_login_returns_jwt(self, client):
        res = _login(client)
        token = res.json()["access_token"]
        # JWT has 3 dot-separated parts
        assert len(token.split(".")) == 3


# ── /me tests ────────────────────────────────────────────────────────────────

class TestMe:
    def test_me_authenticated(self, client):
        token = _login(client).json()["access_token"]
        res = client.get("/api/v2/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        body = res.json()
        assert body["email"] == VALID_EMAIL
        assert body["is_verified"] is True

    def test_me_no_token(self, client):
        res = client.get("/api/v2/auth/me")
        assert res.status_code == 401

    def test_me_invalid_token(self, client):
        res = client.get("/api/v2/auth/me", headers={"Authorization": "Bearer garbage"})
        assert res.status_code == 401


# ── Token refresh tests ───────────────────────────────────────────────────────

class TestRefresh:
    def test_refresh_success(self, client):
        tokens  = _login(client).json()
        res     = client.post("/api/v2/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert res.status_code == 200
        new_tokens = res.json()
        assert "access_token"  in new_tokens
        assert "refresh_token" in new_tokens
        # New tokens should differ from old ones
        assert new_tokens["access_token"]  != tokens["access_token"]
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    def test_refresh_old_token_rejected(self, client):
        """After rotation, the old refresh token must be invalid."""
        tokens = _login(client).json()
        old_refresh = tokens["refresh_token"]
        # Rotate once
        client.post("/api/v2/auth/refresh", json={"refresh_token": old_refresh})
        # Old token should now be rejected
        res = client.post("/api/v2/auth/refresh", json={"refresh_token": old_refresh})
        assert res.status_code == 401

    def test_refresh_invalid_token(self, client):
        res = client.post("/api/v2/auth/refresh", json={"refresh_token": "not.a.token"})
        assert res.status_code == 401


# ── Email verification tests ─────────────────────────────────────────────────

class TestEmailVerification:
    def test_invalid_token_redirects_to_error(self, client):
        res = client.get("/api/v2/auth/verify-email?token=fakebadtoken", follow_redirects=False)
        assert res.status_code in (302, 307)
        assert "verified=error" in res.headers["location"]

    def test_valid_token_verifies_user(self, client):
        # Sign up a fresh user
        email = "verifytest@example.com"
        _signup(client, email=email)
        # Get the token from the DB
        db = _Session()
        from models.user import User
        user = db.query(User).filter(User.email == email).first()
        token = user.verification_token
        db.close()
        # Hit the verify endpoint
        res = client.get(f"/api/v2/auth/verify-email?token={token}", follow_redirects=False)
        assert res.status_code in (302, 307)
        assert "verified=success" in res.headers["location"]
        # User should now be verified
        db = _Session()
        user = db.query(User).filter(User.email == email).first()
        assert user.is_verified is True
        db.close()


# ── Rate limiting tests ───────────────────────────────────────────────────────

class TestRateLimit:
    def test_rate_limit_triggers(self, client):
        """10 failed attempts in a row should return 429."""
        for _ in range(10):
            client.post("/api/v2/auth/login", json={"email": "rl@example.com", "password": "Bad@Pass1"})
        res = client.post("/api/v2/auth/login", json={"email": "rl@example.com", "password": "Bad@Pass1"})
        assert res.status_code == 429


# ── Security header tests ─────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        res = client.get("/api/health")
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("x-xss-protection") == "1; mode=block"
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
