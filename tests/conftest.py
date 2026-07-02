"""Shared test fixtures."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_client():
    """TestClient with a valid admin session cookie.

    Dashboard/API routes sit behind session auth; tests for those endpoints
    must authenticate like the browser does. Settings is a frozen dataclass, so
    the test secret is installed via object.__setattr__ and restored after.
    """
    from app import auth
    from app.config import settings
    from app.main import app

    original_secret = settings.secret_key
    original_hash = settings.admin_password_hash
    object.__setattr__(settings, "secret_key", "test-secret-key-not-default")
    object.__setattr__(settings, "admin_password_hash", "testsalt:00" * 8)

    client = TestClient(app)
    client.cookies.set(auth.SESSION_COOKIE, auth.create_session_token())
    try:
        yield client
    finally:
        object.__setattr__(settings, "secret_key", original_secret)
        object.__setattr__(settings, "admin_password_hash", original_hash)


@pytest.fixture()
def anon_client():
    """Unauthenticated client — for public endpoints and 401 assertions."""
    from app.main import app

    return TestClient(app)
