import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class BookingStatus(str, enum.Enum):
    HELD = "held"
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class StaffRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    RECEPTION = "reception"
    SPECIALIST = "specialist"


class NotificationType(str, enum.Enum):
    BOOKING_CONFIRMED = "booking_confirmed"
    BOOKING_CANCELLED = "booking_cancelled"
    REMINDER_24H = "reminder_24h"
    REMINDER_2H = "reminder_2h"
    STAFF_NEW_BOOKING = "staff_new_booking"
    STAFF_CANCEL = "staff_cancel"
    FORCE_MAJEURE = "force_majeure"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    bot_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bot_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bot_status: Mapped[str] = mapped_column(String(32), default="active")
    brand: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    default_schedule_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_rule.id", ondelete="SET NULL"), nullable=True
    )
    subscription_status: Mapped[str] = mapped_column(String(32), default="trial")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Branch(Base):
    __tablename__ = "branch"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    holidays: Mapped[list[Any]] = mapped_column(JSONB, default=list)


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffMember(Base):
    __tablename__ = "staff_member"
    __table_args__ = (UniqueConstraint("tenant_id", "user_account_id", name="uq_staff_tenant_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    user_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    display_name: Mapped[str] = mapped_column(String(255))
    roles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedule_rule.id", ondelete="SET NULL"), nullable=True
    )
    payout_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ui_prefs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class StaffInvite(Base):
    __tablename__ = "staff_invite"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    staff_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff_member.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    intended_roles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by_user_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientProfile(Base):
    __tablename__ = "client_profile"
    __table_args__ = (
        Index("ix_client_tenant_phone", "tenant_id", "phone"),
        UniqueConstraint("tenant_id", "user_account_id", name="uq_client_tenant_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    user_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    consents: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0)
    telegram_unreachable: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClientChatMessage(Base):
    __tablename__ = "client_chat_message"
    __table_args__ = (Index("ix_client_chat_tenant_client_created", "tenant_id", "client_profile_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    client_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_profile.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(16))
    author: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    staff_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_member.id", ondelete="SET NULL"), nullable=True
    )
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceCategory(Base):
    __tablename__ = "service_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Service(Base):
    __tablename__ = "service"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_category.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))
    price_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)
    revisit_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SpecialistService(Base):
    __tablename__ = "specialist_service"
    __table_args__ = (UniqueConstraint("staff_member_id", "service_id", name="uq_specialist_service"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    staff_member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_member.id", ondelete="CASCADE"))
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service.id", ondelete="CASCADE"))
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ScheduleRule(Base):
    """Недельный шаблон: каждый день недели — пункт правила со своими часами."""

    __tablename__ = "schedule_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    days: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScheduleTemplate(Base):
    __tablename__ = "schedule_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    staff_member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_member.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(8))
    end_time: Mapped[str] = mapped_column(String(8))
    break_start: Mapped[str | None] = mapped_column(String(8), nullable=True)
    break_end: Mapped[str | None] = mapped_column(String(8), nullable=True)


class ScheduleException(Base):
    __tablename__ = "schedule_exception"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    staff_member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_member.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    during: Mapped[Any] = mapped_column(TSTZRANGE)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TimeCell(Base):
    """Legacy optional slot overlay; default booking path uses schedule minus bookings."""

    __tablename__ = "time_cell"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"))
    staff_member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_member.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_service_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Booking(Base):
    __tablename__ = "booking"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"))
    client_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("client_profile.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default=BookingStatus.HELD.value)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_price_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reschedule_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    course_enrollment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["BookingItem"]] = relationship(back_populates="booking", cascade="all, delete-orphan")


class BookingItem(Base):
    __tablename__ = "booking_item"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("booking.id", ondelete="CASCADE"), index=True)
    staff_member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_member.id", ondelete="CASCADE"))
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service.id", ondelete="CASCADE"))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    during: Mapped[Any] = mapped_column(TSTZRANGE)
    blocked_during: Mapped[Any] = mapped_column(TSTZRANGE)
    price_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    cell_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("time_cell.id", ondelete="SET NULL"), nullable=True, index=True
    )

    booking: Mapped["Booking"] = relationship(back_populates="items")


class BookingEvent(Base):
    __tablename__ = "booking_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("booking.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("booking.id", ondelete="CASCADE"), nullable=True)
    recipient_type: Mapped[str] = mapped_column(String(32))
    recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    notification_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=NotificationStatus.PENDING.value)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Resource(Base):
    __tablename__ = "resource"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    resource_type: Mapped[str] = mapped_column(String(64))


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    client_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("client_profile.id", ondelete="CASCADE"))
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service.id", ondelete="CASCADE"))
    staff_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_member.id", ondelete="SET NULL"), nullable=True
    )
    preferred_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    __tablename__ = "review"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("booking.id", ondelete="CASCADE"), unique=True)
    client_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("client_profile.id", ondelete="CASCADE"))
    staff_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salon_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderation_status: Mapped[str] = mapped_column(String(32), default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourseTemplate(Base):
    __tablename__ = "course_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sessions_count: Mapped[int] = mapped_column(Integer)
    min_days_between: Mapped[int] = mapped_column(Integer, default=7)
    max_days_between: Mapped[int] = mapped_column(Integer, default=30)
    validity_days: Mapped[int] = mapped_column(Integer, default=180)
    price_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    is_flexible: Mapped[bool] = mapped_column(Boolean, default=False)


class CourseEnrollment(Base):
    __tablename__ = "course_enrollment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("course_template.id", ondelete="CASCADE"))
    client_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("client_profile.id", ondelete="CASCADE"))
    sessions_completed: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("booking.id", ondelete="SET NULL"), nullable=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    tip_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    method: Mapped[str] = mapped_column(String(32), default="cash")
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Promotion(Base):
    __tablename__ = "promotion"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    segment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PromoCode(Base):
    __tablename__ = "promo_code"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoyaltyRule(Base):
    __tablename__ = "loyalty_rule"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    every_nth_visit: Mapped[int] = mapped_column(Integer, default=5)
    discount_percent: Mapped[int] = mapped_column(Integer, default=10)


class Payout(Base):
    __tablename__ = "payout"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    staff_member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_member.id", ondelete="CASCADE"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformInvoice(Base):
    __tablename__ = "platform_invoice"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantLanding(Base):
    __tablename__ = "tenant_landing"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="CASCADE"), unique=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dgis_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    dgis_firm_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dgis_complex_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dgis_embed_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    map_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    map_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    map_zoom: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LandingPortfolioItem(Base):
    __tablename__ = "landing_portfolio_item"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_urls: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class LandingPost(Base):
    __tablename__ = "landing_post"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    photo_urls: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class LandingProfileWidget(Base):
    __tablename__ = "landing_profile_widget"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    template: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationTemplate(Base):
    __tablename__ = "notification_template"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", name="uq_notification_template_tenant_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenant.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text, default="")
    parse_mode: Mapped[str] = mapped_column(String(16), default="HTML")
    photo_slots: Mapped[list[Any]] = mapped_column(JSONB, default=list)
