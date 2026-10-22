from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_by_public_id, require_role, resolve_staff_and_client
from app.api.subscription_gate import assert_tenant_can_write
from app.core.context import UserContext
from app.core.db import get_session
from app.domain.models import AuditLog, CourseTemplate, Review
from app.domain.services.billing_service import create_subscription_invoice
from app.domain.services.course_service import enroll_client
from app.domain.services.marketing_service import create_promotion, validate_promo_code
from app.domain.services.payment_service import record_payment
from app.domain.services.review_service import create_review, reply_to_review
from app.domain.services.v2.import_service import import_from_csv
from app.domain.services.v2.nl_booking import suggest_slots_from_intent
from app.domain.services.v2.prepayment_service import create_deposit_invoice
from app.domain.services.waitlist_service import join_waitlist
from app.domain.services.v2.gcal_sync import export_staff_day_to_gcal

phase2_router = APIRouter(prefix="/api/v1", tags=["phase2"])


class ReviewCreate(BaseModel):
    booking_id: UUID
    staff_rating: int = Field(ge=1, le=5)
    salon_rating: int = Field(ge=1, le=5)
    text: str | None = None


class WaitlistJoin(BaseModel):
    service_id: UUID
    staff_member_id: UUID | None = None
    preferred_date: datetime | None = None


class CourseEnroll(BaseModel):
    template_id: UUID


class PaymentCreate(BaseModel):
    booking_id: UUID | None = None
    amount_cents: int
    tip_cents: int = 0
    method: str = "cash"


class PromoValidate(BaseModel):
    code: str


class PromotionCreate(BaseModel):
    title: str
    body: str | None = None
    discount_percent: int | None = None
    segment: str | None = None


@phase2_router.post("/reviews")
async def api_create_review(
    body: ReviewCreate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=400, detail="client required")
    try:
        review = await create_review(
            session,
            tenant_id=tenant.id,
            booking_id=body.booking_id,
            client_profile_id=user.client_profile_id,
            staff_rating=body.staff_rating,
            salon_rating=body.salon_rating,
            text=body.text,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": str(review.id)}


@phase2_router.post("/reviews/{review_id}/reply")
async def api_reply_review(
    review_id: UUID,
    reply: str,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("manager", "owner")),
) -> dict[str, str]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    try:
        await reply_to_review(session, tenant_id=tenant.id, review_id=review_id, reply=reply)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok"}


@phase2_router.get("/reviews/public")
async def public_reviews(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(
            select(Review).where(
                Review.tenant_id == tenant.id,
                Review.moderation_status == "published",
            )
        )
    ).all()
    return [
        {
            "staff_rating": r.staff_rating,
            "salon_rating": r.salon_rating,
            "text": r.text,
            "business_reply": r.business_reply,
        }
        for r in rows
    ]


@phase2_router.post("/waitlist")
async def api_waitlist(
    body: WaitlistJoin,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=400, detail="client required")
    entry = await join_waitlist(
        session,
        tenant_id=tenant.id,
        client_profile_id=user.client_profile_id,
        service_id=body.service_id,
        staff_member_id=body.staff_member_id,
        preferred_date=body.preferred_date,
    )
    await session.commit()
    return {"id": str(entry.id)}


@phase2_router.get("/courses/templates")
async def course_templates(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(select(CourseTemplate).where(CourseTemplate.tenant_id == tenant.id))
    ).all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "sessions_count": t.sessions_count,
            "price_cents": t.price_cents,
        }
        for t in rows
    ]


@phase2_router.post("/courses/enroll")
async def course_enroll(
    body: CourseEnroll,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=400, detail="client required")
    try:
        en = await enroll_client(
            session,
            tenant_id=tenant.id,
            template_id=body.template_id,
            client_profile_id=user.client_profile_id,
        )
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": str(en.id)}


@phase2_router.post("/payments")
async def api_payment(
    body: PaymentCreate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("manager", "owner", "specialist")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    payment = await record_payment(
        session,
        tenant_id=tenant.id,
        booking_id=body.booking_id,
        amount_cents=body.amount_cents,
        tip_cents=body.tip_cents,
        method=body.method,
    )
    await session.commit()
    return {"id": str(payment.id)}


@phase2_router.post("/marketing/promotions")
async def api_promotion(
    body: PromotionCreate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("manager", "owner")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    assert_tenant_can_write(tenant)
    promo = await create_promotion(
        session,
        tenant_id=tenant.id,
        title=body.title,
        body=body.body,
        discount_percent=body.discount_percent,
        segment=body.segment,
    )
    await session.commit()
    return {"id": str(promo.id)}


@phase2_router.post("/marketing/promo-code/validate")
async def api_validate_promo(
    body: PromoValidate,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    row = await validate_promo_code(session, tenant_id=tenant.id, code=body.code)
    if row is None:
        raise HTTPException(status_code=404, detail="invalid promo")
    await session.commit()
    return {"discount_percent": row.discount_percent}


@phase2_router.get("/manager/audit-log")
async def audit_log(
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("manager", "owner")),
) -> list[dict]:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    rows = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant.id)
            .order_by(AuditLog.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "action": r.action,
            "entity_type": r.entity_type,
            "created_at": r.created_at.isoformat(),
            "details": r.details,
        }
        for r in rows
    ]


@phase2_router.post("/platform/invoices")
async def platform_invoice(
    amount_cents: int = Query(...),
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("owner")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    inv = await create_subscription_invoice(session, tenant=tenant, amount_cents=amount_cents)
    await session.commit()
    return {"id": str(inv.id), "status": inv.status}


# Phase 3 API surface (stubs wired for future work)
@phase2_router.post("/v2/prepayment/deposit")
async def prepayment_deposit(
    booking_id: UUID,
    amount_cents: int,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(get_current_user),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    return await create_deposit_invoice(
        session, tenant_id=tenant.id, booking_id=booking_id, amount_cents=amount_cents
    )


@phase2_router.post("/v2/import/csv")
async def import_csv(
    source: str,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _: UserContext = Depends(require_role("owner", "manager")),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    return await import_from_csv(session, tenant_id=tenant.id, source=source, rows=[])


@phase2_router.post("/v2/nl-booking/suggest")
async def nl_booking(
    text: str,
    tenant_public_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    user: UserContext = Depends(get_current_user),
) -> dict:
    tenant = await get_tenant_by_public_id(tenant_public_id, session)
    user = await resolve_staff_and_client(session, tenant, user)
    if user.client_profile_id is None:
        raise HTTPException(status_code=400, detail="client required")
    return await suggest_slots_from_intent(
        tenant_id=tenant.id,
        client_profile_id=user.client_profile_id,
        text=text,
    )


@phase2_router.post("/v2/gcal/export")
async def gcal_export(
    tenant_public_id: str = Query(...),
    user: UserContext = Depends(require_role("specialist", "manager", "owner")),
) -> dict:
    if user.staff_member_id is None:
        raise HTTPException(status_code=400, detail="staff required")
    return await export_staff_day_to_gcal(staff_member_id=user.staff_member_id, ical_body="")
