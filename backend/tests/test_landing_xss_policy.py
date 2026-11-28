from app.domain.services.dgis_html import public_dgis_embed_html


def test_public_dgis_embed_strips_script() -> None:
    evil = '<script>alert(1)</script><iframe src="https://evil.example/x"></iframe>'
    assert public_dgis_embed_html(evil) is None


def test_public_dgis_embed_allows_2gis_iframe() -> None:
    raw = '<iframe src="https://widgets.2gis.com/widget?type=firmsonmap"></iframe>'
    safe = public_dgis_embed_html(raw)
    assert safe is not None
    assert "widgets.2gis.com" in safe
    assert "<script" not in safe.lower()