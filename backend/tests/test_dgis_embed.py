import pytest

from app.core.settings import get_settings
from app.domain.services.dgis_embed import (
    build_firmsonmap_embed_src,
    dgis_map_payload,
    normalize_dgis_locations,
    probe_firmsonmap_embed,
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


def test_build_firmsonmap_embed_src_includes_map_center():
    src = build_firmsonmap_embed_src(
        ["70000001065110165"],
        center_lon=38.964322,
        center_lat=45.015825,
        center_zoom=17.0,
    )
    assert src is not None
    assert "pos" in src
    assert "38.964322" in src


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


def test_dgis_map_payload_embed_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGIS_FIRMSONMAP_PROBE", "false")
    get_settings.cache_clear()
    payload = dgis_map_payload(_LegacyLanding())
    assert len(payload["dgis_locations"]) == 1
    assert payload["dgis_embed_src"] is not None
    assert payload["dgis_firmsonmap_embed_enabled"] is True
    assert payload["dgis_locations"][0]["map_lon"] == 38.96
    assert payload["dgis_embed_probe_ok"] is True


def test_dgis_map_payload_embed_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGIS_FIRMSONMAP_EMBED", "false")
    monkeypatch.setenv("DGIS_FIRMSONMAP_PROBE", "false")
    get_settings.cache_clear()
    payload = dgis_map_payload(_LegacyLanding())
    assert payload["dgis_embed_src"] is None
    assert payload["dgis_firmsonmap_embed_enabled"] is False


def test_dgis_map_payload_probe_marks_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGIS_FIRMSONMAP_PROBE", "true")
    get_settings.cache_clear()
    probe_firmsonmap_embed.cache_clear()
    src = build_firmsonmap_embed_src(["70000001065110165"])
    assert src is not None

    def fail_probe(_url: str) -> bool:
        return False

    monkeypatch.setattr("app.domain.services.dgis_embed.probe_firmsonmap_embed", fail_probe)
    payload = dgis_map_payload(_LegacyLanding())
    assert payload["dgis_embed_src"] is not None
    assert payload["dgis_embed_probe_ok"] is False


def test_parse_and_embed_roundtrip():
    url = "https://2gis.ru/krasnodar/firm/70000001065110165/"
    r = parse_dgis_url(url)
    locs = normalize_dgis_locations([url])
    assert locs[0]["firm_id"] == r.firm_id
    assert build_firmsonmap_embed_src([r.firm_id])  # type: ignore[arg-type]