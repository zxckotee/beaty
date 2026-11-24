"""Optional 2GIS Catalog API (Places) for firm coordinates — phase 2, key-gated."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.settings import get_settings

logger = logging.getLogger(__name__)
_CATALOG_BYID = "https://catalog.api.2gis.com/3.0/items/byid"


async def fetch_firm_point(firm_id: str) -> tuple[float, float] | None:
    """Return (lon, lat) for branch id when DGIS_CATALOG_API_KEY is set."""
    key = (get_settings().dgis_catalog_api_key or "").strip()
    if not key or not firm_id:
        return None
    params = {"id": firm_id, "fields": "items.point", "key": key}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_CATALOG_BYID, params=params)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("dgis catalog byid failed for %s: %s", firm_id, exc)
        return None
    items = (data.get("result") or {}).get("items") or []
    if not items:
        return None
    point = items[0].get("point") or {}
    lon, lat = point.get("lon"), point.get("lat")
    if lon is None or lat is None:
        return None
    return float(lon), float(lat)


async def enrich_locations_coords(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill map_lon/map_lat from Catalog when missing and API key is configured."""
    if not (get_settings().dgis_catalog_api_key or "").strip():
        return locations
    out: list[dict[str, Any]] = []
    for loc in locations:
        row = dict(loc)
        if row.get("map_lat") is not None and row.get("map_lon") is not None:
            out.append(row)
            continue
        fid = row.get("firm_id")
        if not fid:
            out.append(row)
            continue
        pt = await fetch_firm_point(str(fid))
        if pt:
            row["map_lon"], row["map_lat"] = pt[0], pt[1]
            if row.get("map_zoom") is None:
                row["map_zoom"] = 17.0
        out.append(row)
    return out