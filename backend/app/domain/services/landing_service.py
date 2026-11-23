from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import NotFoundError
from app.domain.models import LandingPortfolioItem, LandingPost, LandingProfileWidget, Tenant, TenantLanding
from app.domain.services.dgis_url import parse_dgis_url
from app.domain.services.landing_widget_payload import WIDGET_TEMPLATES

_IFRAME_2GIS = re.compile(r"<iframe[\s\S]*?src=[\"'](https://[^\"']*2gis[^\"']*)[\"']", re.IGNORECASE)


def sanitize_dgis_embed(html: str | None) -> str | None:
    if not html or not html.strip():
        return None
    text = html.strip()
    if "<script" in text.lower():
        return None
    m = _IFRAME_2GIS.search(text)
    if not m:
        return None
    src = m.group(1)
    return (
        f'<iframe src="{src}" width="100%" height="100%" style="border:0;" '
        'loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>'
    )


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
    if "dgis_url" in changes:
        raw = changes.pop("dgis_url")
        if raw:
            parsed = parse_dgis_url(str(raw))
            landing.dgis_url = parsed.dgis_url or str(raw).strip()
            if parsed.firm_id:
                landing.dgis_firm_id = parsed.firm_id
            if parsed.map_lon is not None:
                landing.map_lon = parsed.map_lon
            if parsed.map_lat is not None:
                landing.map_lat = parsed.map_lat
            if parsed.map_zoom is not None:
                landing.map_zoom = parsed.map_zoom
        else:
            landing.dgis_url = None
            landing.dgis_firm_id = None
    if "dgis_embed_html" in changes:
        changes["dgis_embed_html"] = sanitize_dgis_embed(changes.get("dgis_embed_html"))
    for key, val in changes.items():
        if hasattr(landing, key):
            setattr(landing, key, val)
    return landing


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