import pytest
from fastapi.testclient import TestClient


def test_health_endpoint():
    from app.main import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "environment" in data
    assert "dry_run" in data


def test_config_status_requires_auth():
    # /config-status leaks integration configuration — must not be public.
    from app.main import app
    client = TestClient(app)
    response = client.get("/config-status")
    assert response.status_code == 401


def test_config_status_structure(auth_client):
    response = auth_client.get("/config-status")
    assert response.status_code == 200
    data = response.json()
    assert "dry_run" in data
    assert "openai_configured" in data
    assert "retell_configured" in data
    assert "sms_configured" in data
    assert "database_configured" in data


def test_config_status_retell_not_configured(auth_client):
    from app.config import settings
    response = auth_client.get("/config-status")
    data = response.json()
    if settings.retell_api_key and not settings.retell_agent_id_en:
        assert data["retell_configured"] is False


def test_config_status_retell_configured(auth_client):
    from app.config import settings
    response = auth_client.get("/config-status")
    data = response.json()
    if settings.retell_api_key and settings.retell_agent_id_en:
        assert data["retell_configured"] is True


def test_mvp_ui_returns_html(auth_client):
    response = auth_client.get("/mvp")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_root_endpoint():
    from app.main import app
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "RE Control Center" in response.text


def test_api_status_endpoint():
    from app.main import app
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "message" in data


# ---------------------------------------------------------------------------
# Auth boundary — endpoints that can send SMS / leak data must reject anon
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/messages/send"),
        ("post", "/follow-ups/run"),
        ("get", "/audit-log"),
        ("get", "/mls/debug"),
        ("get", "/mls/status"),
        ("get", "/leads"),
        ("get", "/config-status"),
    ],
)
def test_sensitive_endpoints_reject_anonymous(method, path):
    from app.main import app
    client = TestClient(app)
    response = getattr(client, method)(path)
    assert response.status_code == 401, f"{method.upper()} {path} must require auth"


def test_lead_create_and_get(auth_client):
    payload = {
        "full_name": "Test User",
        "phone": "+16475551234",
        "email": "test@example.com",
    }
    response = auth_client.post("/leads", json=payload)
    assert response.status_code == 200
    lead = response.json()
    assert lead["full_name"] == "Test User"
    assert lead["phone"] == "+16475551234"
    assert "id" in lead


def test_lead_not_found(auth_client):
    response = auth_client.get("/leads/nonexistent-id-123")
    assert response.status_code == 404


def test_list_leads(auth_client):
    response = auth_client.get("/leads")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# v2 Endpoint tests — no DB configured, expect 503 with helpful messages
# ---------------------------------------------------------------------------

def test_leads_scored_503_without_db(auth_client):
    response = auth_client.get("/leads-scored")
    assert response.status_code == 503
    assert "Database" in response.json()["detail"]


def test_lead_profile_503_without_db(auth_client):
    response = auth_client.get("/leads/any-id/profile")
    assert response.status_code == 503


def test_home_fit_report_503_without_db(auth_client):
    response = auth_client.post(
        "/leads/any-id/home-fit-report",
        json={"lead_id": "any-id", "listing": None}
    )
    assert response.status_code == 503


def test_copilot_query_503_without_db(auth_client):
    response = auth_client.post(
        "/copilot/query",
        json={"query": "What is dual agency?"}
    )
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"] or "Copilot" in response.json()["detail"]


def test_copilot_ingest_503_without_db(auth_client):
    response = auth_client.post(
        "/copilot/ingest",
        json={"text": "test", "doc_id": "test", "source_path": "test.txt"}
    )
    assert response.status_code == 503


def test_copilot_ingest_pdf_503_without_db(auth_client):
    response = auth_client.post(
        "/copilot/ingest-pdf",
        json={"pdf_path": "/fake/path.pdf", "doc_id": "test-doc"}
    )
    assert response.status_code == 503


def test_all_new_routes_registered():
    from app.main import app
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    required = {
        "/leads-scored",
        "/leads/{lead_id}/profile",
        "/leads/{lead_id}/home-fit-report",
        "/copilot/query",
        "/copilot/ingest",
        "/copilot/ingest-pdf",
        "/webhooks/twilio/status",
    }
    assert required.issubset(paths), f"Missing routes: {required - paths}"


def test_version_updated():
    from app.main import app
    assert app.version == "0.3.0"


# ---------------------------------------------------------------------------
# Twilio webhook signature enforcement
# ---------------------------------------------------------------------------

def test_twilio_inbound_rejects_unsigned_when_db_configured():
    """Forged (unsigned) Twilio posts must be rejected. Without DB the endpoint
    503s first; with DB it must 403 before touching anything."""
    from app.main import app, orchestrator_repo
    client = TestClient(app)
    response = client.post(
        "/webhooks/twilio/sms",
        data={"From": "+16475550000", "Body": "STOP", "MessageSid": "SMfake"},
    )
    if orchestrator_repo is None:
        assert response.status_code == 503
    else:
        assert response.status_code == 403


def test_twilio_signature_verification_roundtrip():
    """verify_twilio_signature accepts a correctly-signed request and rejects
    a tampered one."""
    import base64
    import hmac
    from hashlib import sha1

    from app.orchestrator.crypto import verify_twilio_signature

    url = "https://example.onrender.com/webhooks/twilio/sms"
    params = {"From": "+16475550000", "Body": "hello", "MessageSid": "SM123"}
    token = "test_auth_token"

    payload = url + "".join(k + params[k] for k in sorted(params))
    good_sig = base64.b64encode(
        hmac.new(token.encode(), payload.encode(), sha1).digest()
    ).decode()

    assert verify_twilio_signature(url, params, token, good_sig) is True
    assert verify_twilio_signature(url, params, token, "forged") is False
    tampered = dict(params, Body="STOP")
    assert verify_twilio_signature(url, tampered, token, good_sig) is False
    assert verify_twilio_signature(url, params, "", good_sig) is False
    assert verify_twilio_signature(url, params, token, None) is False
