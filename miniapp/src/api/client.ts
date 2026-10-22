const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

export type Service = {
  id: string;
  name: string;
  price_cents: number;
  duration_minutes: number;
};

export type Specialist = { id: string; display_name: string; photo_url?: string | null };

export type Booking = {
  id: string;
  status: string;
  total_price_cents: number;
  hold_expires_at?: string | null;
};

export async function authTelegram(tenantPublicId: string, initData: string) {
  return apiFetch("/api/v1/auth/telegram", {
    method: "POST",
    body: JSON.stringify({ tenant_public_id: tenantPublicId, init_data: initData }),
  }) as Promise<{ access_token: string }>;
}

export async function fetchServices(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/services?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<Service[]>;
}

export async function fetchSpecialists(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/specialists?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<Specialist[]>;
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

export async function fetchMyBookings(tenantPublicId: string) {
  return apiFetch(
    `/api/v1/bookings/mine?tenant_public_id=${encodeURIComponent(tenantPublicId)}`,
  ) as Promise<Booking[]>;
}
