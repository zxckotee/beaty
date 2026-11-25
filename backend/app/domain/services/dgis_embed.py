"""Build 2GIS firms-on-map widget embed URLs from firm ids (no API key)."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import httpx

from app.core.settings import get_settings
from app.domain.models import TenantLanding
from app.domain.services.dgis_url import parse_dgis_url

logger = logging.getLogger(__name__)

_MAX_FIRMS = 20
_FIRMSONMAP_WIDGET = "https://widgets.2gis.com/widget"
_MAX_IFRAME_SRC_LEN = 4096


_EMBED_FAIL_MARKERS = (
    "something went wrong",
    "ошибочка вышла",
    "отказываются отвечать",
)


def build_firmsonmap_embed_src(
    firm_ids: list[str],
    *,
    center_lon: float | None = None,
    center_lat: float | None = None,
    center_zoom: float | None = None,
) -> str | None:
    ids: list[str] = []
    seen: set[str] = set()
    for raw in firm_ids:
        fid = (raw or "").strip()
        if not fid or fid in seen:
            continue
        seen.add(fid)
        ids.append(fid)
        if len(ids) >= _MAX_FIRMS:
            break
    if not ids:
        return None
    opts: dict[str, Any] = {"org": ",".join(ids)}
    if center_lon is not None and center_lat is not None:
        pos: dict[str, Any] = {"lon": center_lon, "lat": center_lat}
        if center_zoom is not None:
            pos["zoom"] = center_zoom
        opts["pos"] = pos
    options = json.dumps(opts, ensure_ascii=False, separators=(",", ":"))
    src = f"{_FIRMSONMAP_WIDGET}?type=firmsonmap&options={quote(options)}"
    if len(src) > _MAX_IFRAME_SRC_LEN:
        return None
    return src


@lru_cache(maxsize=64)
def probe_firmsonmap_embed(embed_src: str) -> bool:
    """Return False when widget HTML is an error page."""
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            resp = client.get(embed_src)
            if resp.status_code >= 400:
                return False
            body = (resp.text or "").lower()
            return not any(marker in body for marker in _EMBED_FAIL_MARKERS)
    except httpx.HTTPError as exc:
        logger.warning("firmsonmap probe failed: %s", exc)
        return False


def build_firmsonmap_iframe_html(embed_src: str) -> str:
    return (
        f'<iframe src="{embed_src}" width="100%" height="100%" style="border:0;" '
        'loading="lazy" referrerpolicy="no-referrer-when-downgrade" '
        'allow="geolocation"></iframe>'
    )


def location_from_url(raw: str, *, label: str | None = None) -> dict[str, Any] | None:
    parsed = parse_dgis_url(raw)
    if not parsed.firm_id:
        return None
    loc: dict[str, Any] = {
        "firm_id": parsed.firm_id,
        "dgis_url": parsed.dgis_url or str(raw).strip(),
    }
    if label and label.strip():
        loc["label"] = label.strip()[:120]
    if parsed.map_lon is not None:
        loc["map_lon"] = parsed.map_lon
    if parsed.map_lat is not None:
        loc["map_lat"] = parsed.map_lat
    if parsed.map_zoom is not None:
        loc["map_zoom"] = parsed.map_zoom
    return loc


def normalize_dgis_locations(raw: list[Any] | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    by_firm: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, str):
            url = item.strip()
            label = None
        elif isinstance(item, dict):
            url = str(item.get("dgis_url") or item.get("url") or "").strip()
            label = item.get("label")
        else:
            continue
        if not url:
            continue
        loc = location_from_url(url, label=str(label) if label else None)
        if loc is None:
            continue
        fid = loc["firm_id"]
        if fid in by_firm:
            if loc.get("label") and not by_firm[fid].get("label"):
                by_firm[fid]["label"] = loc["label"]
            continue
        by_firm[fid] = loc
        if len(by_firm) >= _MAX_FIRMS:
            break
    return list(by_firm.values())


def landing_locations_from_row(landing: TenantLanding) -> list[dict[str, Any]]:
    stored = getattr(landing, "dgis_locations", None) or []
    if stored:
        return list(stored)
    legacy: list[dict[str, Any]] = []
    firm_id = getattr(landing, "dgis_firm_id", None)
    dgis_url = getattr(landing, "dgis_url", None)
    if firm_id and dgis_url:
        entry: dict[str, Any] = {"firm_id": firm_id, "dgis_url": dgis_url}
        if landing.map_lon is not None:
            entry["map_lon"] = landing.map_lon
        if landing.map_lat is not None:
            entry["map_lat"] = landing.map_lat
        if landing.map_zoom is not None:
            entry["map_zoom"] = landing.map_zoom
        legacy.append(entry)
    return legacy


def sync_legacy_dgis_fields(landing: TenantLanding, locations: list[dict[str, Any]]) -> None:
    if not locations:
        landing.dgis_url = None
        landing.dgis_firm_id = None
        landing.map_lon = None
        landing.map_lat = None
        landing.map_zoom = None
        return
    primary = locations[0]
    landing.dgis_url = primary.get("dgis_url")
    landing.dgis_firm_id = primary.get("firm_id")
    landing.map_lon = primary.get("map_lon")
    landing.map_lat = primary.get("map_lat")
    landing.map_zoom = primary.get("map_zoom")


def dgis_map_payload(landing: TenantLanding) -> dict[str, Any]:
    locations = landing_locations_from_row(landing)
    firm_ids = [str(x["firm_id"]) for x in locations if x.get("firm_id")]
    firmsonmap_enabled = bool(get_settings().dgis_firmsonmap_embed)
    embed_src: str | None = None
    embed_html: str | None = None
    center_lon = landing.map_lon
    center_lat = landing.map_lat
    center_zoom = landing.map_zoom
    if locations:
        primary = locations[0]
        if primary.get("map_lon") is not None:
            center_lon = primary.get("map_lon")
        if primary.get("map_lat") is not None:
            center_lat = primary.get("map_lat")
        if primary.get("map_zoom") is not None:
            center_zoom = primary.get("map_zoom")
    if firmsonmap_enabled:
        embed_src = build_firmsonmap_embed_src(
            firm_ids,
            center_lon=float(center_lon) if center_lon is not None else None,
            center_lat=float(center_lat) if center_lat is not None else None,
            center_zoom=float(center_zoom) if center_zoom is not None else None,
        )
        if embed_src:
            embed_html = build_firmsonmap_iframe_html(embed_src)
    legacy_html = getattr(landing, "dgis_embed_html", None)
    if embed_html is None and legacy_html and str(legacy_html).strip():
        embed_html = str(legacy_html).strip()
    settings = get_settings()
    probe_ok = False
    if embed_src and settings.dgis_firmsonmap_probe:
        probe_ok = probe_firmsonmap_embed(embed_src)
    elif embed_src:
        probe_ok = True
    return {
        "dgis_locations": locations,
        "dgis_embed_src": embed_src,
        "dgis_embed_html": embed_html,
        "dgis_firmsonmap_embed_enabled": firmsonmap_enabled,
        "dgis_embed_probe_ok": probe_ok,
    }