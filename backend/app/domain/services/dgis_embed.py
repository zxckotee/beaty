"""Build 2GIS firms-on-map widget embed URLs from firm ids (no API key)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from app.domain.services.dgis_url import parse_dgis_url

_MAX_FIRMS = 20
_FIRMSONMAP_WIDGET = "https://widgets.2gis.com/widget"
_MAX_IFRAME_SRC_LEN = 4096


def build_firmsonmap_embed_src(firm_ids: list[str]) -> str | None:
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
    options = json.dumps({"org": ",".join(ids)}, ensure_ascii=False, separators=(",", ":"))
    src = f"{_FIRMSONMAP_WIDGET}?type=firmsonmap&options={quote(options)}"
    if len(src) > _MAX_IFRAME_SRC_LEN:
        return None
    return src


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
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
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
        if loc is None or loc["firm_id"] in seen:
            continue
        seen.add(loc["firm_id"])
        out.append(loc)
        if len(out) >= _MAX_FIRMS:
            break
    return out


def landing_locations_from_row(landing) -> list[dict[str, Any]]:
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


def sync_legacy_dgis_fields(landing, locations: list[dict[str, Any]]) -> None:
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


def dgis_map_payload(landing) -> dict[str, Any]:
    locations = landing_locations_from_row(landing)
    firm_ids = [str(x["firm_id"]) for x in locations if x.get("firm_id")]
    embed_src = build_firmsonmap_embed_src(firm_ids)
    embed_html = build_firmsonmap_iframe_html(embed_src) if embed_src else None
    legacy_html = getattr(landing, "dgis_embed_html", None)
    if embed_html is None and legacy_html and str(legacy_html).strip():
        embed_html = str(legacy_html).strip()
    return {
        "dgis_locations": locations,
        "dgis_embed_src": embed_src,
        "dgis_embed_html": embed_html,
    }