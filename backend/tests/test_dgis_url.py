from app.domain.services.dgis_url import parse_dgis_url


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