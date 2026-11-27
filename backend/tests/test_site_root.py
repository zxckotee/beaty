from fastapi.testclient import TestClient

from app.web.main import app


def test_production_root_serves_platform_landing(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("WEB_DEV_LOGIN", "true")
    monkeypatch.setenv("WEB_DEFAULT_TENANT", "")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/")
        assert r.status_code == 200
        assert "Beaty-Welcome" in r.text
        assert "platform.css" in r.text
        assert "unsafe-eval" in r.headers.get("content-security-policy", "")
        assert client.get("/login").status_code == 404
        meta = client.get("/api/platform").json()
        assert meta["product"] == "Beaty-Welcome"
        assert meta["demo_tenant_id"] is None
    finally:
        get_settings.cache_clear()


def test_platform_meta_includes_demo_tenant(monkeypatch) -> None:
    monkeypatch.setenv("WEB_DEFAULT_TENANT", "demo-salon")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        meta = client.get("/api/platform").json()
        assert meta["demo_tenant_id"] == "demo-salon"
        r = client.get("/")
        assert r.status_code == 200
        assert "data-demo-link" in r.text
    finally:
        get_settings.cache_clear()


def test_platform_docs_api_and_page() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/docs").status_code == 200
    payload = client.get("/api/docs/platform").json()
    assert payload["product"] == "Beaty-Welcome"
    platform_sections = [s for s in payload["sections"] if s.get("id", "").startswith("platform-")]
    assert len(platform_sections) >= 6
    onboard = next(s for s in platform_sections if s["id"] == "platform-onboard")
    assert onboard.get("bullets") or onboard.get("body") or onboard.get("paragraphs")
    r = client.get("/legal/privacy")
    assert r.status_code == 200
    assert "152-ФЗ" in r.text
    assert "legal-article" in r.text
