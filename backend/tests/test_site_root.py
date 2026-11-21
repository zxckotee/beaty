from fastapi.testclient import TestClient

from app.web.main import app


def test_production_root_is_not_tenant_directory(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("WEB_DEV_LOGIN", "true")
    monkeypatch.setenv("WEB_DEFAULT_TENANT", "")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/")
        assert r.status_code == 404
        assert client.get("/login").status_code == 404
    finally:
        get_settings.cache_clear()


def test_production_root_redirects_default_tenant(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("WEB_DEFAULT_TENANT", "demo-salon")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "/t/demo-salon/"
    finally:
        get_settings.cache_clear()