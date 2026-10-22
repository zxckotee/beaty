import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchStaffDay,
  setBookingStatus,
  declareUnavailable,
  type StaffBooking,
} from "../api/client";

export function StaffDayPage({ tenantPublicId }: { tenantPublicId: string }) {
  const qc = useQueryClient();
  const day = useQuery({
    queryKey: ["staff-day", tenantPublicId],
    queryFn: () => fetchStaffDay(tenantPublicId),
  });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      setBookingStatus(tenantPublicId, id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staff-day", tenantPublicId] }),
  });

  const unavailableMut = useMutation({
    mutationFn: () => declareUnavailable(tenantPublicId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staff-day", tenantPublicId] }),
  });

  return (
    <div className="page">
      <div className="card-row" style={{ marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Мой день</h2>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ width: "auto", padding: "8px 12px" }}
          onClick={() => unavailableMut.mutate()}
        >
          Форс-мажор
        </button>
      </div>

      {day.isLoading && <p className="muted">Загрузка…</p>}
      {day.data?.map((b: StaffBooking) => (
        <div key={b.booking_id} className="card">
          <div className="card-row">
            <strong>
              {new Date(b.start_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </strong>
            <span>{b.status}</span>
          </div>
          <p>{b.client_name}</p>
          <p className="muted">{b.service_name}</p>
          {b.comment && <p className="muted">{b.comment}</p>}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
            {(["arrived", "completed", "no_show"] as const).map((st) => (
              <button
                key={st}
                type="button"
                className="chip"
                onClick={() => statusMut.mutate({ id: b.booking_id, status: st })}
              >
                {st === "arrived" ? "Пришёл" : st === "completed" ? "Готово" : "Неявка"}
              </button>
            ))}
          </div>
        </div>
      ))}
      {!day.data?.length && !day.isLoading && <p className="muted">Сегодня записей нет</p>}
    </div>
  );
}
