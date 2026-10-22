import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchManagerCalendar,
  fetchReschedulePending,
  fetchServices,
  fetchStaff,
  type CalendarItem,
} from "../api/client";

export function ManagerPage({ tenantPublicId }: { tenantPublicId: string }) {
  const calendar = useQuery({
    queryKey: ["manager-calendar", tenantPublicId],
    queryFn: () => fetchManagerCalendar(tenantPublicId),
  });
  const pending = useQuery({
    queryKey: ["reschedule-pending", tenantPublicId],
    queryFn: () => fetchReschedulePending(tenantPublicId),
  });
  const staff = useQuery({
    queryKey: ["manager-staff", tenantPublicId],
    queryFn: () => fetchStaff(tenantPublicId),
  });
  const services = useQuery({
    queryKey: ["services", tenantPublicId],
    queryFn: () => fetchServices(tenantPublicId),
  });

  const [tab, setTab] = useState<"day" | "pending" | "team">("day");

  return (
    <div className="page">
      <div className="nav-tabs" style={{ marginBottom: 16 }}>
        {(["day", "pending", "team"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
            style={{ border: "none", cursor: "pointer" }}
          >
            {t === "day" ? "День" : t === "pending" ? "Форс-мажор" : "Команда"}
          </button>
        ))}
      </div>

      {tab === "day" && (
        <>
          <h2>Календарь</h2>
          {calendar.isLoading && <p className="muted">Загрузка…</p>}
          {calendar.data?.map((item: CalendarItem) => (
            <div key={item.booking_id} className="card">
              <div className="card-row">
                <strong>{item.start_at ? new Date(item.start_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}</strong>
                <span>{item.status}</span>
              </div>
              <p>{item.client_name}</p>
              <p className="muted">
                {item.service_name} · {item.staff_name}
              </p>
              {item.reschedule_pending && <p className="error">Требует решения</p>}
            </div>
          ))}
          {!calendar.data?.length && !calendar.isLoading && (
            <p className="muted">На сегодня записей нет</p>
          )}
        </>
      )}

      {tab === "pending" && (
        <>
          <h2>Нерешённые переносы</h2>
          {pending.data?.map((p) => (
            <div key={p.id} className="card">
              Запись {p.id.slice(0, 8)}… — {p.status}
            </div>
          ))}
          {!pending.data?.length && <p className="muted">Всё решено</p>}
        </>
      )}

      {tab === "team" && (
        <>
          <h2>Мастера и услуги</h2>
          {staff.data?.map((s) => (
            <div key={s.id} className="card">
              <strong>{s.display_name}</strong>
              <p className="muted">{s.roles?.join(", ")}</p>
            </div>
          ))}
          <h3 style={{ marginTop: 24 }}>Услуги</h3>
          {services.data?.map((svc) => (
            <div key={svc.id} className="card card-row">
              <span>{svc.name}</span>
              <span>{(svc.price_cents / 100).toFixed(0)} ₽</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
