from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domain.services import review_service
from app.web.deps import WebContext, get_context, require_auth, require_manager

router = APIRouter(prefix="/api/t/{tenant_public_id}", tags=["reviews"])


def _mask_name(name: str | None) -> str:
    raw = (name or "Клиент").strip()
    if len(raw) <= 2:
        return raw[0] + "*" if raw else "Клиент"
    return raw[0] + "*" * (len(raw) - 2) + raw[-1]


def _review_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "salon_rating": row["salon_rating"],
        "staff_rating": row.get("staff_rating"),
        "text": row.get("text"),
        "business_reply": row.get("business_reply"),
        "client_name": _mask_name(row.get("client_name")),
        "created_at": (
            row["created_at"].isoformat()
            if isinstance(row.get("created_at"), datetime)
            else row.get("created_at")
        ),
    }


@router.get("/reviews")
async def list_reviews(
    ctx: WebContext = Depends(get_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows, avg = await review_service.list_published_for_tenant(session, tenant_id=ctx.tenant.id)
    return {
        "avg_salon_rating": avg,
        "items": [_review_dict(r) for r in rows],
    }


@router.get("/reviews/reviewable")
async def reviewable_bookings(
    ctx: WebContext = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if ctx.client is None:
        raise HTTPException(status_code=403, detail="clients only")
    items = await review_service.list_reviewable_bookings(
        session, tenant_id=ctx.tenant.id, client_profile_id=ctx.client.id
    )
    return {
        "bookings": [
            {
                "booking_id": str(b["booking_id"]),
                "starts_at": b["starts_at"].isoformat() if b.get("starts_at") else None,
                "service_names": b.get("service_names") or [],
            }
            for b in items
        ],
    }


class CreateReviewBody(BaseModel):
    booking_id: UUID
    salon_rating: int = Field(ge=1, le=5)
    staff_rating: int | None = Field(default=None, ge=1, le=5)
    text: str | None = Field(default=None, max_length=2000)


@router.post("/reviews")
async def create_review(
    body: CreateReviewBody,
    ctx: WebContext = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if ctx.client is None:
        raise HTTPException(status_code=403, detail="clients only")
    try:
        review = await review_service.create_review_for_client(
            session,
            tenant_id=ctx.tenant.id,
            booking_id=body.booking_id,
            client_profile_id=ctx.client.id,
            salon_rating=body.salon_rating,
            staff_rating=body.staff_rating,
            text=body.text,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=400, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    return {"id": str(review.id)}


class ReplyBody(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)


@router.post("/manager/reviews/{review_id}/reply")
async def manager_reply(
    review_id: UUID,
    body: ReplyBody,
    ctx: WebContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        review = await review_service.reply_to_review(
            session, tenant_id=ctx.tenant.id, review_id=review_id, reply=body.reply
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": str(review.id), "business_reply": review.business_reply}