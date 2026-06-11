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


def test_config_status_structure():
    from app.main import app
    client = TestClient(app)
    response = client.get("/config-status")
    assert response.status_code == 200
    data = response.json()
    assert "dry_run" in data
    assert "openai_configured" in data
    assert "retell_configured" in data
    assert "sms_configured" in data
    assert "database_configured" in data


def test_config_status_retell_not_configured():
    from app.main import app
    from app.config import settings
    client = TestClient(app)
    # If RETELL_API_KEY is set but RETELL_AGENT_ID_EN is empty, retell is not configured
    response = client.get("/config-status")
    data = response.json()
    if settings.retell_api_key and not settings.retell_agent_id_en:
        assert data["retell_configured"] is False


def test_config_status_retell_configured():
    from app.main import app
    from app.config import settings
    client = TestClient(app)
    response = client.get("/config-status")
    data = response.json()
    if settings.retell_api_key and settings.retell_agent_id_en:
        assert data["retell_configured"] is True


def test_mvp_ui_returns_html():
    from app.main import app
    client = TestClient(app)
    response = client.get("/mvp")
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


def test_lead_create_and_get():
    from app.main import app
    client = TestClient(app)
    payload = {
        "full_name": "Test User",
        "phone": "+16475551234",
        "email": "test@example.com",
    }
    response = client.post("/leads", json=payload)
    assert response.status_code == 200
    lead = response.json()
    assert lead["full_name"] == "Test User"
    assert lead["phone"] == "+16475551234"
    assert "id" in lead


def test_lead_not_found():
    from app.main import app
    client = TestClient(app)
    response = client.get("/leads/nonexistent-id-123")
    assert response.status_code == 404


def test_list_leads():
    from app.main import app
    client = TestClient(app)
    response = client.get("/leads")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# v2 Endpoint tests — no DB configured, expect 503 with helpful messages
# ---------------------------------------------------------------------------

def test_leads_scored_503_without_db():
    from app.main import app
    client = TestClient(app)
    response = client.get("/leads-scored")
    assert response.status_code == 503
    assert "Database" in response.json()["detail"]


def test_lead_profile_503_without_db():
    from app.main import app
    client = TestClient(app)
    response = client.get("/leads/any-id/profile")
    assert response.status_code == 503


def test_home_fit_report_503_without_db():
    from app.main import app
    client = TestClient(app)
    response = client.post(
        "/leads/any-id/home-fit-report",
        json={"lead_id": "any-id", "listing": None}
    )
    assert response.status_code == 503


def test_copilot_query_503_without_db():
    from app.main import app
    client = TestClient(app)
    response = client.post(
        "/copilot/query",
        json={"query": "What is dual agency?"}
    )
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"] or "Copilot" in response.json()["detail"]


def test_copilot_ingest_503_without_db():
    from app.main import app
    client = TestClient(app)
    response = client.post(
        "/copilot/ingest",
        json={"text": "test", "doc_id": "test", "source_path": "test.txt"}
    )
    assert response.status_code == 503


def test_copilot_ingest_pdf_503_without_db():
    from app.main import app
    client = TestClient(app)
    response = client.post(
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
    }
    assert required.issubset(paths), f"Missing routes: {required - paths}"


def test_version_updated():
    from app.main import app
    assert app.version == "0.3.0"
