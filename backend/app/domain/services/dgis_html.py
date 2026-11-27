"""Safe handling of legacy 2GIS embed HTML (strip scripts; only allow iframe from 2GIS hosts)."""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

_2GIS_HOST_SUFFIXES = (".2gis.ru", ".2gis.com", "2gis.ru", "2gis.com")
_ALLOWED_IFRAME_HOSTS = (
    "widgets.2gis.com",
    "widget.2gis.com",
    "map-widget.api.2gis.com",
)


def _host_ok(host: str) -> bool:
    h = (host or "").lower()
    if h in _ALLOWED_IFRAME_HOSTS:
        return True
    return any(h.endswith(sfx) for sfx in _2GIS_HOST_SUFFIXES)


def _extract_iframe_src(raw: str) -> str | None:
    class _IframeSrc(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.src: str | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag.lower() != "iframe" or self.src is not None:
                return
            for k, v in attrs:
                if k.lower() == "src" and v:
                    self.src = v.strip()
                    return

    parser = _IframeSrc()
    try:
        parser.feed(raw)
    except Exception:
        return None
    if not parser.src:
        return None
    try:
        host = urlparse(parser.src).hostname or ""
    except Exception:
        return None
    if not _host_ok(host):
        return None
    return parser.src


def public_dgis_embed_html(raw: str | None) -> str | None:
    """Return sanitized iframe HTML for public clients, or None if unsafe / empty."""
    if not raw or not str(raw).strip():
        return None
    src = _extract_iframe_src(str(raw))
    if not src:
        return None
    safe_src = escape(src, quote=True)
    return (
        f'<iframe src="{safe_src}" width="100%" height="100%" style="border:0;" '
        'title="Карта 2ГИС" loading="lazy" allow="geolocation"></iframe>'
    )