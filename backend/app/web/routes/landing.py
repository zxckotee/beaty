from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.models import LandingPortfolioItem, LandingPost, LandingProfileWidget, Tenant
from app.domain.services.dgis_embed import dgis_map_payload, normalize_dgis_locations
from app.domain.services.dgis_url import dgis_parse_to_dict, parse_dgis_url
from app.domain.services.landing_service import (
    get_or_create_landing,
    get_portfolio_item,
    get_post,
    get_widget,
    list_portfolio,
    list_posts,
    list_widgets,
    reorder_widgets,
    update_landing,
    validate_template,
)
from app.domain.services.landing_widget_payload import normalize_widget_payload
from app.web.deps import WebContext, get_tenant, require_manager, writable
from app.web.uploads import save_image

public_router = APIRouter(prefix="/api/t/{tenant_public_id}/landing", tags=["landing"])
manager_router = APIRouter(prefix="/api/t/{tenant_public_id}/manager/landing", tags=["landing-manager"])


def _widget_dict(w: LandingProfileWidget) -> dict[str, object]:
    return {
        "id": str(w.id),
        "template": w.template,
        "payload": w.payload or {},
        "sort_order": w.sort_order,
        "is_visible": w.is_visible,
    }


def _landing_dict(
    landing,
    portfolio,
    posts,
    widgets,
    *,
    tenant: Tenant,
) -> dict[str, object]:
    dgis = dgis_map_payload(landing)
    return {
        "title": landing.title or tenant.name,
        "tagline": landing.tagline,
        "cover_url": landing.cover_url,
        "avatar_url": landing.avatar_url,
        "dgis_url": landing.dgis_url,
        "dgis_firm_id": landing.dgis_firm_id,
        "dgis_locations": dgis["dgis_locations"],
        "dgis_embed_src": dgis["dgis_embed_src"],
        "dgis_embed_html": dgis["dgis_embed_html"],
        "map_lon": landing.map_lon,
        "map_lat": landing.map_lat,
        "map_zoom": landing.map_zoom,
        "bot_username": tenant.bot_username,
        "portfolio": [
            {
                "id": str(p.id),
                "title": p.title,
                "description": p.description,
                "photo_urls": p.photo_urls or [],
                "sort_order": p.sort_order,
            }
            for p in portfolio
        ],
        "posts": [
            {
                "id": str(p.id),
                "title": p.title,
                "body": p.body,
                "photo_urls": p.photo_urls or [],
                "sort_order": p.sort_order,
            }
            for p in posts
        ],
        "widgets": [_widget_dict(w) for w in widgets],
    }


@public_router.get("")
async def public_landing(
    tenant: Tenant = Depends(get_tenant), session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    landing = await get_or_create_landing(session, tenant.id)
    await session.commit()
    portfolio = await list_portfolio(session, tenant.id)
    posts = await list_posts(session, tenant.id, visible_only=True)
    widgets = await list_widgets(session, tenant.id, visible_only=True)
    return _landing_dict(landing, portfolio, posts, widgets, tenant=tenant)


class DgisLocationIn(BaseModel):
    dgis_url: str = Field(min_length=4, max_length=2000)
    label: str | None = Field(default=None, max_length=120)


class LandingPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    tagline: str | None = Field(default=None, max_length=4000)
    dgis_url: str | None = None
    dgis_locations: list[DgisLocationIn] | None = Field(default=None, max_length=20)
    dgis_embed_html: str | None = Field(default=None, max_length=12000)


class DgisParseIn(BaseModel):
    url: str = Field(min_length=4, max_length=2000)


class PortfolioIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    photo_urls: list[str] = Field(default_factory=list, max_length=20)
    sort_order: int = 0


class PortfolioPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    photo_urls: list[str] | None = Field(default=None, max_length=20)
    sort_order: int | None = None


class PostIn(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(default="", max_length=8000)
    photo_urls: list[str] = Field(default_factory=list, max_length=20)
    sort_order: int = 0
    is_visible: bool = True


class PostPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=8000)
    photo_urls: list[str] | None = Field(default=None, max_length=20)
    sort_order: int | None = None
    is_visible: bool | None = None


@manager_router.get("")
async def manager_get_landing(
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    landing = await get_or_create_landing(session, tenant.id)
    portfolio = await list_portfolio(session, tenant.id)
    posts = await list_posts(session, tenant.id, visible_only=False)
    widgets = await list_widgets(session, tenant.id, visible_only=False)
    return _landing_dict(landing, portfolio, posts, widgets, tenant=tenant)


@manager_router.patch("")
async def manager_patch_landing(
    body: LandingPatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    changes = body.model_dump(exclude_unset=True)
    landing = await update_landing(session, tenant=tenant, changes=changes)
    portfolio = await list_portfolio(session, tenant.id)
    posts = await list_posts(session, tenant.id, visible_only=False)
    widgets = await list_widgets(session, tenant.id, visible_only=False)
    await session.commit()
    return _landing_dict(landing, portfolio, posts, widgets, tenant=tenant)


class WidgetIn(BaseModel):
    template: str = Field(min_length=1, max_length=32)
    payload: dict[str, object] = Field(default_factory=dict)
    sort_order: int = 0
    is_visible: bool = True


class WidgetPatch(BaseModel):
    template: str | None = Field(default=None, max_length=32)
    payload: dict[str, object] | None = None
    sort_order: int | None = None
    is_visible: bool | None = None


class WidgetReorderItem(BaseModel):
    id: UUID
    sort_order: int


class WidgetReorderIn(BaseModel):
    items: list[WidgetReorderItem] = Field(min_length=1, max_length=50)


@manager_router.post("/dgis/parse")
async def manager_parse_dgis(
    body: DgisParseIn,
    ctx: WebContext = Depends(require_manager),
) -> dict[str, object]:
    writable(ctx)
    return dgis_parse_to_dict(parse_dgis_url(body.url))


@manager_router.post("/photo/cover")
async def upload_cover(
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    url = await save_image(file, tenant.id)
    landing = await update_landing(session, tenant=tenant, changes={"cover_url": url})
    await session.commit()
    return {"cover_url": landing.cover_url}


@manager_router.post("/photo/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    url = await save_image(file, tenant.id)
    landing = await update_landing(session, tenant=tenant, changes={"avatar_url": url})
    await session.commit()
    return {"avatar_url": landing.avatar_url}


@manager_router.post("/portfolio")
async def create_portfolio(
    body: PortfolioIn,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    item = LandingPortfolioItem(
        tenant_id=tenant.id,
        title=body.title,
        description=body.description,
        photo_urls=body.photo_urls,
        sort_order=body.sort_order,
    )
    session.add(item)
    await session.commit()
    return {
        "id": str(item.id),
        "title": item.title,
        "description": item.description,
        "photo_urls": item.photo_urls,
        "sort_order": item.sort_order,
    }


@manager_router.patch("/portfolio/{item_id}")
async def patch_portfolio(
    item_id: UUID,
    body: PortfolioPatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    item = await get_portfolio_item(session, tenant.id, item_id)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(item, key, val)
    await session.commit()
    return {
        "id": str(item.id),
        "title": item.title,
        "description": item.description,
        "photo_urls": item.photo_urls,
        "sort_order": item.sort_order,
    }


@manager_router.delete("/portfolio/{item_id}")
async def delete_portfolio(
    item_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    item = await get_portfolio_item(session, tenant.id, item_id)
    await session.delete(item)
    await session.commit()
    return {"status": "ok"}


@manager_router.post("/portfolio/{item_id}/photos")
async def upload_portfolio_photo(
    item_id: UUID,
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    item = await get_portfolio_item(session, tenant.id, item_id)
    url = await save_image(file, tenant.id)
    photos = list(item.photo_urls or [])
    photos.append(url)
    item.photo_urls = photos[:20]
    await session.commit()
    return {"photo_urls": item.photo_urls}


@manager_router.post("/posts")
async def create_post(
    body: PostIn,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    post = LandingPost(
        tenant_id=tenant.id,
        title=body.title,
        body=body.body,
        photo_urls=body.photo_urls,
        sort_order=body.sort_order,
        is_visible=body.is_visible,
    )
    session.add(post)
    await session.commit()
    return {
        "id": str(post.id),
        "title": post.title,
        "body": post.body,
        "photo_urls": post.photo_urls,
        "sort_order": post.sort_order,
        "is_visible": post.is_visible,
    }


@manager_router.patch("/posts/{post_id}")
async def patch_post(
    post_id: UUID,
    body: PostPatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    post = await get_post(session, tenant.id, post_id)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(post, key, val)
    await session.commit()
    return {
        "id": str(post.id),
        "title": post.title,
        "body": post.body,
        "photo_urls": post.photo_urls,
        "sort_order": post.sort_order,
        "is_visible": post.is_visible,
    }


@manager_router.delete("/posts/{post_id}")
async def delete_post(
    post_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    post = await get_post(session, tenant.id, post_id)
    await session.delete(post)
    await session.commit()
    return {"status": "ok"}


@manager_router.post("/posts/{post_id}/photos")
async def upload_post_photo(
    post_id: UUID,
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    post = await get_post(session, tenant.id, post_id)
    url = await save_image(file, tenant.id)
    photos = list(post.photo_urls or [])
    photos.append(url)
    post.photo_urls = photos[:20]
    await session.commit()
    return {"photo_urls": post.photo_urls}


@manager_router.post("/widgets")
async def create_widget(
    body: WidgetIn,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    template = validate_template(body.template)
    payload = normalize_widget_payload(body.payload)
    widget = LandingProfileWidget(
        tenant_id=tenant.id,
        template=template,
        payload=payload,
        sort_order=body.sort_order,
        is_visible=body.is_visible,
    )
    session.add(widget)
    await session.commit()
    return _widget_dict(widget)


@manager_router.patch("/widgets/{widget_id}")
async def patch_widget(
    widget_id: UUID,
    body: WidgetPatch,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    widget = await get_widget(session, tenant.id, widget_id)
    data = body.model_dump(exclude_unset=True)
    if "template" in data and data["template"] is not None:
        widget.template = validate_template(data["template"])
    if "payload" in data and data["payload"] is not None:
        widget.payload = normalize_widget_payload(data["payload"])
    if "sort_order" in data:
        widget.sort_order = data["sort_order"]
    if "is_visible" in data:
        widget.is_visible = data["is_visible"]
    await session.commit()
    return _widget_dict(widget)


@manager_router.delete("/widgets/{widget_id}")
async def delete_widget(
    widget_id: UUID,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    widget = await get_widget(session, tenant.id, widget_id)
    await session.delete(widget)
    await session.commit()
    return {"status": "ok"}


@manager_router.put("/widgets/reorder")
async def reorder_landing_widgets(
    body: WidgetReorderIn,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    tenant = writable(ctx)
    await reorder_widgets(
        session,
        tenant.id,
        [(item.id, item.sort_order) for item in body.items],
    )
    await session.commit()
    return {"status": "ok"}


@manager_router.post("/widgets/{widget_id}/photos")
async def upload_widget_photo(
    widget_id: UUID,
    file: UploadFile = File(...),
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant = writable(ctx)
    widget = await get_widget(session, tenant.id, widget_id)
    url = await save_image(file, tenant.id)
    payload = dict(widget.payload or {})
    photos = list(payload.get("photos") or [])
    if len(photos) >= 5:
        raise HTTPException(status_code=400, detail="photo limit 5")
    photos.append(url)
    payload["photos"] = photos
    widget.payload = normalize_widget_payload(payload)
    await session.commit()
    return {"photos": widget.payload.get("photos", [])}