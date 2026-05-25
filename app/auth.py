"""
Minimal stdlib-only session auth.

No external packages — uses hmac + hashlib + base64 from Python stdlib.

Session token format: base64url(payload_json).HMAC-SHA256-hex
Payload: {"sub": "admin", "exp": <unix_timestamp>}

Password verification: PBKDF2-HMAC-SHA256 (stored as hex in ADMIN_PASSWORD_HASH).
To generate a hash locally:
    python -c "
    import hashlib, secrets, binascii
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', b'yourpassword', salt.encode(), 260000)
    print(salt + ':' + binascii.hexlify(h).decode())
    "
Then set ADMIN_PASSWORD_HASH=<output> in Render env vars.

If ADMIN_PASSWORD_HASH is not set, auth is disabled (returns 503).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Cookie, HTTPException, Request, Response

from app.config import settings

SESSION_COOKIE = "admin_session"


# ---------------------------------------------------------------------------
# Token creation + verification
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _sign(payload: dict[str, Any], secret: str) -> str:
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _verify(token: str, secret: str) -> dict[str, Any] | None:
    """Return payload dict if token is valid and not expired, else None."""
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    body, sig = parts
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(body))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def create_session_token() -> str:
    exp = int(time.time()) + settings.session_ttl_hours * 3600
    return _sign({"sub": "admin", "exp": exp}, settings.secret_key)


def verify_session_token(token: str) -> bool:
    if not settings.secret_key or settings.secret_key == "change-me-in-production":
        return False
    return _verify(token, settings.secret_key) is not None


# ---------------------------------------------------------------------------
# Password verification (PBKDF2)
# ---------------------------------------------------------------------------

def verify_password(plain: str) -> bool:
    """Verify plain-text password against ADMIN_PASSWORD_HASH (salt:hex)."""
    stored = settings.admin_password_hash
    if not stored:
        return False
    parts = stored.split(":", 1)
    if len(parts) != 2:
        return False
    salt, expected_hex = parts
    computed = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
    computed_hex = binascii.hexlify(computed).decode()
    return hmac.compare_digest(computed_hex, expected_hex)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def require_admin(request: Request) -> None:
    """FastAPI dependency — raises 401 if session cookie is missing or invalid."""
    if not settings.admin_password_hash:
        raise HTTPException(status_code=503, detail="Auth not configured. Set ADMIN_PASSWORD_HASH.")
    token = request.cookies.get(SESSION_COOKIE)
    if not token or not verify_session_token(token):
        raise HTTPException(status_code=401, detail="Not authenticated.")


def set_session_cookie(response: Response) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(),
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
