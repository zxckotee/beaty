from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuthTelegramRequest(BaseModel):
    tenant_public_id: str
    init_data: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    user_account_id: UUID
    roles: list[str]
    client_profile_id: UUID | None = None
    staff_member_id: UUID | None = None
    tenant_public_id: str
    tenant_name: str
    brand: dict


class ServiceOut(BaseModel):
    id: UUID
    name: str
    price_cents: int
    duration_minutes: int
    category_id: UUID | None = None


class SpecialistOut(BaseModel):
    id: UUID
    display_name: str
    photo_url: str | None = None


class SlotOut(BaseModel):
    start: datetime
    end: datetime
    staff_member_id: UUID | None = None


class HoldBookingRequest(BaseModel):
    staff_member_id: UUID
    service_id: UUID
    start_at: datetime


class BookingOut(BaseModel):
    id: UUID
    status: str
    total_price_cents: int
    hold_expires_at: datetime | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None


class BookingStatusUpdate(BaseModel):
    status: str = Field(description="arrived|completed|no_show")
