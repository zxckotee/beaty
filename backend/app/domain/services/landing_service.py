from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import NotFoundError
from app.domain.models import LandingPortfolioItem, LandingPost, LandingProfileWidget, Tenant, TenantLanding
from app.domain.services.dgis_catalog import enrich_locations_coords
from app.domain.services.dgis_embed import landing_locations_from_row, normalize_dgis_locations, sync_legacy_dgis_fields
from app.domain.services.landing_widget_payload import WIDGET_TEMPLATES


async def get_or_create_landing(session: AsyncSession, tenant_id: uuid.UUID) -> TenantLanding:
    landing = await session.scalar(select(TenantLanding).where(TenantLanding.tenant_id == tenant_id))
    if landing is None:
        landing = TenantLanding(tenant_id=tenant_id)
        session.add(landing)
        await session.flush()
    return landing


async def update_landing(
    session: AsyncSession,
    *,
    tenant: Tenant,
    changes: dict[str, Any],
) -> TenantLanding:
    landing = await get_or_create_landing(session, tenant.id)
    if "dgis_locations" in changes:
        locs = normalize_dgis_locations(changes.pop("dgis_locations"))
        locs = await enrich_locations_coords(locs)
        landing.dgis_locations = locs
        landing.dgis_embed_html = None
        sync_legacy_dgis_fields(landing, locs)
    elif "dgis_url" in changes:
        raw = changes.pop("dgis_url")
        if raw:
            locs = await enrich_locations_coords(
                normalize_dgis_locations([{"dgis_url": str(raw).strip()}])
            )
            landing.dgis_locations = locs
            landing.dgis_embed_html = None
            sync_legacy_dgis_fields(landing, locs)
        else:
            landing.dgis_locations = []
            landing.dgis_embed_html = None
            sync_legacy_dgis_fields(landing, [])
    if "dgis_embed_html" in changes:
        changes.pop("dgis_embed_html")
    for key, val in changes.items():
        if hasattr(landing, key):
            setattr(landing, key, val)
    return landing


def persist_legacy_dgis_locations(landing: TenantLanding) -> bool:
    """Copy legacy dgis_url row into dgis_locations JSON when column is still empty."""
    if landing.dgis_locations:
        return False
    locs = landing_locations_from_row(landing)
    if not locs:
        return False
    landing.dgis_locations = locs
    return True


async def list_portfolio(session: AsyncSession, tenant_id: uuid.UUID) -> list[LandingPortfolioItem]:
    rows = await session.scalars(
        select(LandingPortfolioItem)
        .where(LandingPortfolioItem.tenant_id == tenant_id)
        .order_by(LandingPortfolioItem.sort_order, LandingPortfolioItem.title)
    )
    return list(rows.all())


async def list_posts(session: AsyncSession, tenant_id: uuid.UUID, *, visible_only: bool) -> list[LandingPost]:
    q = select(LandingPost).where(LandingPost.tenant_id == tenant_id)
    if visible_only:
        q = q.where(LandingPost.is_visible.is_(True))
    rows = await session.scalars(q.order_by(LandingPost.sort_order.desc(), LandingPost.id))
    return list(rows.all())


async def get_portfolio_item(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> LandingPortfolioItem:
    item = await session.get(LandingPortfolioItem, item_id)
    if item is None or item.tenant_id != tenant_id:
        raise NotFoundError("portfolio item not found")
    return item


async def get_post(session: AsyncSession, tenant_id: uuid.UUID, post_id: uuid.UUID) -> LandingPost:
    post = await session.get(LandingPost, post_id)
    if post is None or post.tenant_id != tenant_id:
        raise NotFoundError("post not found")
    return post


async def list_widgets(
    session: AsyncSession, tenant_id: uuid.UUID, *, visible_only: bool
) -> list[LandingProfileWidget]:
    q = select(LandingProfileWidget).where(LandingProfileWidget.tenant_id == tenant_id)
    if visible_only:
        q = q.where(LandingProfileWidget.is_visible.is_(True))
    rows = await session.scalars(q.order_by(LandingProfileWidget.sort_order, LandingProfileWidget.id))
    return list(rows.all())


async def get_widget(
    session: AsyncSession, tenant_id: uuid.UUID, widget_id: uuid.UUID
) -> LandingProfileWidget:
    widget = await session.get(LandingProfileWidget, widget_id)
    if widget is None or widget.tenant_id != tenant_id:
        raise NotFoundError("widget not found")
    return widget


def validate_template(template: str) -> str:
    t = (template or "").strip().lower()
    if t not in WIDGET_TEMPLATES:
        raise ValueError("unknown widget template")
    return t


async def reorder_widgets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: list[tuple[uuid.UUID, int]],
) -> None:
    if not order:
        return
    ids = [wid for wid, _ in order]
    rows = await session.scalars(
        select(LandingProfileWidget).where(
            LandingProfileWidget.tenant_id == tenant_id,
            LandingProfileWidget.id.in_(ids),
        )
    )
    by_id = {w.id: w for w in rows.all()}
    for wid, sort_order in order:
        if wid in by_id:
            by_id[wid].sort_order = sort_order