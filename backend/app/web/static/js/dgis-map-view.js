/** Shared rules for 2GIS locations vs OSM map vs optional iframe embed. */

export function firmCardUrl(point) {
  if (!point) return null;
  if (point.dgis_url) return String(point.dgis_url);
  if (point.firm_id) return `https://2gis.ru/firm/${point.firm_id}`;
  return null;
}

export function mapPointsFromData(d) {
  if (!d) return [];
  const pts = [];
  for (const loc of d.dgis_locations || []) {
    if (loc.map_lat != null && loc.map_lon != null) {
      pts.push({
        lat: Number(loc.map_lat),
        lon: Number(loc.map_lon),
        label: loc.label || '',
        dgis_url: loc.dgis_url || null,
        firm_id: loc.firm_id || null,
      });
    }
  }
  if (!pts.length && d.map_lat != null && d.map_lon != null) {
    pts.push({
      lat: Number(d.map_lat),
      lon: Number(d.map_lon),
      label: d.title || '',
      dgis_url: d.dgis_url || null,
      firm_id: d.dgis_firm_id || null,
    });
  }
  return pts;
}

export function hasInteractiveMapPoints(d) {
  return mapPointsFromData(d).length > 0;
}

export function hasDgisIframe(d) {
  if (!d) return false;
  if (d.dgis_embed_src) return true;
  return Boolean(d.dgis_embed_html && String(d.dgis_embed_html).trim());
}

/** Prefer interactive 2GIS firmsonmap when embed URL passes server probe. */
export function shouldShowDgisEmbedPrimary(d) {
  if (!hasDgisIframe(d)) return false;
  return d.dgis_embed_probe_ok !== false;
}

/** Saved branch links and/or legacy embed — not the same as a working iframe. */
export function hasDgisBranches(d) {
  if (!d) return false;
  if (d.dgis_locations && d.dgis_locations.length) return true;
  if (d.dgis_url) return true;
  return hasDgisIframe(d);
}

export function bindMarkerToDgisCard(marker, point) {
  const title = point.label || 'Организация';
  const url = firmCardUrl(point);
  if (url) {
    marker.bindPopup(`${title}<br>Нажмите — открыть карточку в 2ГИС`);
    marker.on('click', () => {
      window.open(url, '_blank', 'noopener,noreferrer');
    });
  } else if (point.label) {
    marker.bindPopup(point.label);
  }
  return marker;
}

export function createOsmMapLayer(L, mapEl) {
  const map = L.map(mapEl, { scrollWheelZoom: false, attributionControl: false });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '',
    maxZoom: 19,
  }).addTo(map);
  return map;
}

/** Add Leaflet markers for OSM fallback; click opens native 2GIS firm page (card). */
export function addOsmMarkers(map, points, data, L) {
  const markers = [];
  const zoom = data.map_zoom || 16;
  for (const p of points) {
    const m = L.marker([p.lat, p.lon]).addTo(map);
    bindMarkerToDgisCard(m, p);
    markers.push(m);
  }
  if (points.length === 1) {
    map.setView([points[0].lat, points[0].lon], zoom);
  } else if (markers.length) {
    map.fitBounds(L.featureGroup(markers).getBounds().pad(0.12));
  }
  setTimeout(() => map.invalidateSize(), 200);
  return markers;
}