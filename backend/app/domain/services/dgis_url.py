"""Parse 2GIS firm URLs; resolve go.2gis.com short links via redirect."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

_FIRM_ID = re.compile(r"/firm/([0-9]+)", re.IGNORECASE)
_COORDS_PATH = re.compile(r"/firm/[0-9]+/([0-9.]+)(?:[,%]2C|,)([0-9.]+)", re.IGNORECASE)
_MAP_QUERY = re.compile(r"m=([0-9.]+)(?:[,%]2C|,)([0-9.]+)/([0-9.]+)", re.IGNORECASE)
_SHORT_LINK = re.compile(r"^https?://(?:go|link)\.2gis\.(?:com|ru)/", re.IGNORECASE)


@dataclass(frozen=True)
class DgisParseResult:
    firm_id: str | None
    dgis_url: str | None
    map_lon: float | None
    map_lat: float | None
    map_zoom: float | None


def _normalized_input(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    return text


def needs_dgis_resolve(raw: str | None) -> bool:
    text = _normalized_input(raw)
    if not text:
        return False
    if _SHORT_LINK.match(text):
        return True
    parsed = urlparse(text)
    if "2gis" not in (parsed.netloc or "").lower():
        return False
    return parse_dgis_url(text).firm_id is None


@lru_cache(maxsize=128)
def resolve_dgis_url(raw: str | None) -> str | None:
    """Follow redirects for go.2gis.com / link.2gis.* until a firm URL is found."""
    text = _normalized_input(raw)
    if not text:
        return None
    if not needs_dgis_resolve(text):
        return text
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(text)
            final = str(resp.url).split("?", 1)[0] if resp.url else text
            full = str(resp.url) if resp.url else text
            if parse_dgis_url(full).firm_id:
                return full
            if parse_dgis_url(final).firm_id:
                return full
    except httpx.HTTPError as exc:
        logger.warning("dgis short link resolve failed for %s: %s", text, exc)
    return text


def parse_dgis_url_resolved(raw: str | None) -> DgisParseResult:
    resolved = resolve_dgis_url(raw)
    return parse_dgis_url(resolved if resolved else raw)


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