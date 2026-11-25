/** Shared rules for 2GIS locations vs OSM map vs optional iframe embed. */

export function mapPointsFromData(d) {
  if (!d) return [];
  const pts = [];
  for (const loc of d.dgis_locations || []) {
    if (loc.map_lat != null && loc.map_lon != null) {
      pts.push({ lat: Number(loc.map_lat), lon: Number(loc.map_lon), label: loc.label || '' });
    }
  }
  if (!pts.length && d.map_lat != null && d.map_lon != null) {
    pts.push({ lat: Number(d.map_lat), lon: Number(d.map_lon), label: d.title || '' });
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

/** Saved branch links and/or legacy embed — not the same as a working iframe. */
export function hasDgisBranches(d) {
  if (!d) return false;
  if (d.dgis_locations && d.dgis_locations.length) return true;
  if (d.dgis_url) return true;
  return hasDgisIframe(d);
}