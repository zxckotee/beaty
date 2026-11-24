import pytest

from app.domain.services.dgis_catalog import enrich_locations_coords


@pytest.mark.asyncio
async def test_enrich_skips_without_api_key():
    locs = [{"firm_id": "123", "dgis_url": "https://2gis.ru/firm/123"}]
    out = await enrich_locations_coords(locs)
    assert out == locs