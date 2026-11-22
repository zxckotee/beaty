"""Parse 2GIS firm URLs without HTTP (firm id, map center, zoom)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

_FIRM_ID = re.compile(r"/firm/([0-9]+)", re.IGNORECASE)
_COORDS_PATH = re.compile(r"/firm/[0-9]+/([0-9.]+)(?:[,%]2C|,)([0-9.]+)", re.IGNORECASE)
_MAP_QUERY = re.compile(r"m=([0-9.]+)(?:[,%]2C|,)([0-9.]+)/([0-9.]+)", re.IGNORECASE)


@dataclass(frozen=True)
class DgisParseResult:
    firm_id: str | None
    dgis_url: str | None
    map_lon: float | None
    map_lat: float | None
    map_zoom: float | None


def parse_dgis_url(raw: str | None) -> DgisParseResult:
    if not raw or not str(raw).strip():
        return DgisParseResult(None, None, None, None, None)
    text = str(raw).strip()
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    parsed = urlparse(text)
    if "2gis" not in (parsed.netloc or "").lower():
        return DgisParseResult(None, None, None, None, None)

    path = unquote(parsed.path or "")
    firm_m = _FIRM_ID.search(path)
    firm_id = firm_m.group(1) if firm_m else None

    map_lon: float | None = None
    map_lat: float | None = None
    map_zoom: float | None = None

    coord_m = _COORDS_PATH.search(path) or _COORDS_PATH.search(unquote(text))
    if coord_m:
        map_lon, map_lat = float(coord_m.group(1)), float(coord_m.group(2))

    query = unquote(parsed.query or "")
    qm = _MAP_QUERY.search(query) or _MAP_QUERY.search(text)
    if qm:
        map_lon, map_lat = float(qm.group(1)), float(qm.group(2))
        map_zoom = float(qm.group(3))
    elif map_lon is not None:
        map_zoom = 17.0

    dgis_url = text.split("?", 1)[0] if firm_id else text
    if firm_id and not dgis_url.endswith(firm_id):
        dgis_url = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")

    return DgisParseResult(firm_id, dgis_url, map_lon, map_lat, map_zoom)


def dgis_parse_to_dict(result: DgisParseResult) -> dict[str, Any]:
    return {
        "firm_id": result.firm_id,
        "dgis_url": result.dgis_url,
        "map_lon": result.map_lon,
        "map_lat": result.map_lat,
        "map_zoom": result.map_zoom,
    }