import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  cancelBooking,
  fetchMyBookings,
  fetchSlots,
  rescheduleBooking,
  type Booking,
} from "../api/client";

type Props = { tenantPublicId: string };

export function MyBookingsPage({ tenantPublicId }: Props) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["my-bookings", tenantPublicId],
    queryFn: () => fetchMyBookings(tenantPublicId),
  });
  const [rescheduleId, setRescheduleId] = useState<string | null>(null);
  const [serviceIdForReschedule, setServiceIdForReschedule] = useState<string | null>(null);

  const slots = useQuery({
    queryKey: ["reschedule-slots", tenantPublicId, serviceIdForReschedule],
    queryFn: () =>
      fetchSlots(tenantPublicId, { service_id: serviceIdForReschedule! }),
    enabled: !!serviceIdForReschedule,
  });

  const cancelMut = useMutation({
    mutationFn: (id: string) => cancelBooking(tenantPublicId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-bookings", tenantPublicId] }),
  });

  const rescheduleMut = useMutation({
    mutationFn: ({ id, start }: { id: string; start: string }) =>
      rescheduleBooking(tenantPublicId, id, start),
    onSuccess: () => {
      setRescheduleId(null);
      qc.invalidateQueries({ queryKey: ["my-bookings", tenantPublicId] });
    },
  });

  if (q.isLoading) return <p className="muted">Загрузка…</p>;

  return (
    <div className="page">
      <h2>Мои записи</h2>
      {q.data?.map((b: Booking) => (
        <div key={b.id} className="card">
          <div className="card-row">
            <strong>{b.service_name ?? "Услуга"}</strong>
            <span>{b.status}</span>
          </div>
          <p className="muted">{b.staff_name}</p>
          {b.start_at && <p>{new Date(b.start_at).toLocaleString()}</p>}
          <p>{(b.total_price_cents / 100).toFixed(0)} ₽</p>
          {!["cancelled", "completed"].includes(b.status) && (
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button type="button" className="btn btn-ghost" onClick={() => cancelMut.mutate(b.id)}>
                Отменить
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  setRescheduleId(b.id);
                  setServiceIdForReschedule(b.service_id ?? null);
                }}
              >
                Перенести
              </button>
            </div>
          )}
        </div>
      ))}

      {rescheduleId && (
        <div className="card">
          <h3>Новое время</h3>
          <div className="chip-grid">
            {slots.data?.slice(0, 12).map((sl) => (
              <button
                key={sl.start}
                type="button"
                className="chip"
                onClick={() =>
                  rescheduleMut.mutate({ id: rescheduleId, start: sl.start })
                }
              >
                {new Date(sl.start).toLocaleString(undefined, {
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
