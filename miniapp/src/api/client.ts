const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(text || res.statusText, res.status);
  }
  if (res.status === 204) return null;
  return res.json();
}

export type MeResponse = {
  roles: string[];
  tenant_name: string;
  brand: Record<string, unknown>;
  subscription_status: string;
};

export type Service = {
  id: string;
  name: string;
  price_cents: number;
  duration_minutes: number;
};

export type Specialist = { id: string; display_name: string; photo_url?: string | null };

export type Slot = { start: string; end: string; staff_member_id?: string | null };

export type Booking = {
  id: string;
  status: string;
  total_price_cents: number;
  hold_expires_at?: string | null;
  start_at?: string | null;
  end_at?: string | null;
  service_name?: string | null;
  staff_name?: string | null;
  service_id?: string | null;
};

export type CalendarItem = {
  booking_id: string;
  client_name: string;
  service_name: string;
  staff_member_id: string;
  staff_name: string;
  start_at: string;
  end_at: string;
  status: string;
  reschedule_pending: boolean;
};

export type StaffBooking = {
  booking_id: string;
  client_name: string;
  service_name: string;
  start_at: string;
  end_at: string;
  status: string;
  comment?: string | null;
};

export async function authTelegram(tenantPublicId: string, initData: string) {
  return apiFetch("/api/v1/auth/telegram", {
    method: "POST",
    body: JSON.stringify({ tenant_public_id: tenantPublicId, init_data: initData }),
  }) as Promise<{ access_token: string; refresh_token?: string }>;
}

export async function fetchMe(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/me?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<MeResponse>;
}

export async function fetchTenantBrand(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/tenant/brand?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<{ brand: Record<string, unknown> }>;
}

export async function fetchServices(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/services?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<Service[]>;
}

export async function fetchSpecialists(tenantPublicId: string, serviceId?: string) {
  const q = new URLSearchParams({ tenant_public_id: tenantPublicId });
  if (serviceId) q.set("service_id", serviceId);
  return apiFetch(`/api/v1/specialists?${q}`) as Promise<Specialist[]>;
}

export async function fetchSlots(
  tenantPublicId: string,
  params: { service_id: string; staff_member_id?: string },
) {
  const q = new URLSearchParams({
    tenant_public_id: tenantPublicId,
    service_id: params.service_id,
  });
  if (params.staff_member_id) q.set("staff_member_id", params.staff_member_id);
  return apiFetch(`/api/v1/slots?${q}`) as Promise<Slot[]>;
}

export async function holdBooking(
  tenantPublicId: string,
  body: { staff_member_id: string; service_id: string; start_at: string },
) {
  return apiFetch(
    `/api/v1/bookings/hold?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
    { method: "POST", body: JSON.stringify(body) },
  ) as Promise<Booking>;
}

export async function confirmBooking(tenantPublicId: string, bookingId: string) {
  return apiFetch(
    `/api/v1/bookings/${bookingId}/confirm?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
    { method: "POST" },
  ) as Promise<Booking>;
}

export async function cancelBooking(tenantPublicId: string, bookingId: string) {
  return apiFetch(
    `/api/v1/bookings/${bookingId}?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
    { method: "DELETE" },
  );
}

export async function rescheduleBooking(tenantPublicId: string, bookingId: string, start_at: string) {
  return apiFetch(
    `/api/v1/bookings/${bookingId}/reschedule?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
    { method: "POST", body: JSON.stringify({ start_at }) },
  ) as Promise<Booking>;
}

export async function fetchMyBookings(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/bookings/mine?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<Booking[]>;
}

export async function fetchManagerCalendar(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/manager/calendar?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<CalendarItem[]>;
}

export async function fetchReschedulePending(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/manager/reschedule-pending?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<{ id: string; status: string }[]>;
}

export async function fetchStaff(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/manager/staff?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<{ id: string; display_name: string; roles: string[] }[]>;
}

export async function fetchStaffDay(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/staff/day?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<StaffBooking[]>;
}

export async function setBookingStatus(tenantPublicId: string, bookingId: string, status: string) {
  return apiFetch(
    `/api/v1/staff/bookings/${bookingId}/status?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
    { method: "POST", body: JSON.stringify({ status }) },
  );
}

export async function declareUnavailable(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/staff/unavailable?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
    { method: "POST", body: JSON.stringify({}) },
  );
}
