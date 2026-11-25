import pytest

from app.core.settings import get_settings
from app.domain.services.dgis_embed import (
    build_firmsonmap_embed_src,
    dgis_map_payload,
    normalize_dgis_locations,
)
from app.domain.services.dgis_url import parse_dgis_url


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_build_firmsonmap_embed_src_single():
    src = build_firmsonmap_embed_src(["70000001065110165"])
    assert src is not None
    assert "widgets.2gis.com/widget" in src
    assert "firmsonmap" in src
    assert "70000001065110165" in src


def test_build_firmsonmap_embed_src_multi():
    src = build_firmsonmap_embed_src(["70000001065110165", "141265770712989"])
    assert src is not None
    assert "70000001065110165" in src
    assert "141265770712989" in src


def test_normalize_dgis_locations_dedup():
    url = "https://2gis.ru/moscow/firm/141265770712989"
    locs = normalize_dgis_locations([url, url, {"dgis_url": url, "label": "Салон"}])
    assert len(locs) == 1
    assert locs[0]["firm_id"] == "141265770712989"
    assert locs[0].get("label") == "Салон"


class _LegacyLanding:
    dgis_locations = []
    dgis_firm_id = "70000001065110165"
    dgis_url = "https://2gis.ru/krasnodar/firm/70000001065110165/"
    map_lon = 38.96
    map_lat = 45.01
    map_zoom = 17.0
    dgis_embed_html = None


def test_dgis_map_payload_legacy_row_embed_disabled_by_default():
    payload = dgis_map_payload(_LegacyLanding())
    assert len(payload["dgis_locations"]) == 1
    assert payload["dgis_embed_src"] is None
    assert payload["dgis_firmsonmap_embed_enabled"] is False
    assert payload["dgis_locations"][0]["map_lon"] == 38.96


def test_dgis_map_payload_firmsonmap_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGIS_FIRMSONMAP_EMBED", "true")
    get_settings.cache_clear()
    payload = dgis_map_payload(_LegacyLanding())
    assert payload["dgis_embed_src"] is not None
    assert "firmsonmap" in payload["dgis_embed_src"]
    assert payload["dgis_firmsonmap_embed_enabled"] is True


def test_parse_and_embed_roundtrip():
    url = "https://2gis.ru/krasnodar/firm/70000001065110165/"
    r = parse_dgis_url(url)
    locs = normalize_dgis_locations([url])
    assert locs[0]["firm_id"] == r.firm_id
    assert build_firmsonmap_embed_src([r.firm_id])  # type: ignore[arg-type]