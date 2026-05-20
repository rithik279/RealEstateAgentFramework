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
    assert "message" in response.json()


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
