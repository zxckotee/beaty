from app.domain.services.dgis_embed import normalize_dgis_locations
from app.domain.services.dgis_url import parse_dgis_url, parse_dgis_url_resolved, resolve_dgis_url


def test_parse_full_krasnodar_url():
    url = (
        "https://2gis.ru/krasnodar/firm/70000001065110165/"
        "38.964322%2C45.015825?m=38.965119%2C45.015168%2F17.68"
    )
    r = parse_dgis_url(url)
    assert r.firm_id == "70000001065110165"
    assert r.map_lon == 38.965119
    assert r.map_lat == 45.015168
    assert r.map_zoom == 17.68
    assert r.dgis_url is not None
    assert "70000001065110165" in r.dgis_url


def test_parse_short_firm_only():
    r = parse_dgis_url("https://2gis.ru/moscow/firm/141265770712989")
    assert r.firm_id == "141265770712989"
    assert r.map_lon is None
    assert r.map_lat is None


def test_parse_empty():
    r = parse_dgis_url("")
    assert r.firm_id is None


def test_parse_non_2gis():
    r = parse_dgis_url("https://example.com/firm/123")
    assert r.firm_id is None


def test_resolve_short_link_mocked(monkeypatch):
    final = "https://2gis.ru/krasnodar/firm/3237945779887750/39.031188,45.019835"

    class _Resp:
        url = final

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, _url):
            return _Resp()

    monkeypatch.setattr("app.domain.services.dgis_url.httpx.Client", _Client)
    resolve_dgis_url.cache_clear()
    resolved = resolve_dgis_url("https://go.2gis.com/udOWv")
    assert resolved == final
    r = parse_dgis_url_resolved("https://go.2gis.com/udOWv")
    assert r.firm_id == "3237945779887750"
    locs = normalize_dgis_locations(["https://go.2gis.com/udOWv"])
    assert len(locs) == 1
    assert locs[0]["firm_id"] == "3237945779887750"