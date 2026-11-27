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
        assert "Beaty" in r.text
        assert "platform.css" in r.text
        assert client.get("/login").status_code == 404
        meta = client.get("/api/platform").json()
        assert meta["product"] == "Beaty"
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
    assert payload["product"] == "Beaty"
    assert any(s["id"] == "platform-onboard" for s in payload["sections"])
    assert client.get("/legal/privacy").status_code == 200