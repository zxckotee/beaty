import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  confirmBooking,
  fetchServices,
  fetchSlots,
  fetchSpecialists,
  holdBooking,
  type Service,
  type Slot,
  type Specialist,
} from "../api/client";

type EntryMode = "service" | "specialist" | "time";
type Props = { tenantPublicId: string };

export function ClientBookingPage({ tenantPublicId }: Props) {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const entry = (params.get("entry")?.split("_")[0] as EntryMode) || "service";
  const preService = params.get("entry")?.startsWith("service_") ? params.get("entry")!.slice(8) : null;
  const preStaff = params.get("entry")?.startsWith("master_") ? params.get("entry")!.slice(7) : null;

  const [mode] = useState<EntryMode>(
    preStaff ? "specialist" : preService ? "service" : entry === "time" ? "time" : "service",
  );
  const [step, setStep] = useState(0);
  const [service, setService] = useState<Service | null>(null);
  const [specialist, setSpecialist] = useState<Specialist | null>(null);
  const [anyStaff, setAnyStaff] = useState(false);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(null);
  const [holdExpires, setHoldExpires] = useState<string | null>(null);

  const services = useQuery({
    queryKey: ["services", tenantPublicId],
    queryFn: () => fetchServices(tenantPublicId),
  });

  const specialists = useQuery({
    queryKey: ["specialists", tenantPublicId, service?.id],
    queryFn: () => fetchSpecialists(tenantPublicId, service!.id),
    enabled: !!service,
  });

  const slots = useQuery({
    queryKey: ["slots", tenantPublicId, service?.id, anyStaff ? null : specialist?.id],
    queryFn: () =>
      fetchSlots(tenantPublicId, {
        service_id: service!.id,
        staff_member_id: anyStaff ? undefined : specialist?.id,
      }),
    enabled: !!service && (anyStaff || !!specialist),
  });

  const steps = useMemo(() => {
    if (mode === "specialist") return ["specialist", "service", "time", "confirm"];
    if (mode === "time") return ["time", "service", "specialist", "confirm"];
    return ["service", "specialist", "time", "confirm"];
  }, [mode]);

  const hold = useMutation({
    mutationFn: () =>
      holdBooking(tenantPublicId, {
        staff_member_id: slot!.staff_member_id ?? specialist!.id,
        service_id: service!.id,
        start_at: slot!.start,
      }),
    onSuccess: (b) => {
      setBookingId(b.id);
      setHoldExpires(b.hold_expires_at ?? null);
      setStep(steps.length - 1);
    },
  });

  const confirm = useMutation({
    mutationFn: () => confirmBooking(tenantPublicId, bookingId!),
  });

  if (services.isLoading) return <p className="muted">{t("common.loading")}</p>;
  if (services.error) return <p className="error">{t("common.error")}</p>;

  const selectedStaffName =
    anyStaff && slot?.staff_member_id
      ? specialists.data?.find((s) => s.id === slot.staff_member_id)?.display_name ?? "Мастер"
      : specialist?.display_name;

  return (
    <div className="page">
      <div className="stepper">
        {steps.map((_, i) => (
          <span key={i} className={i <= step ? "on" : ""} />
        ))}
      </div>

      {step === steps.indexOf("service") && (
        <>
          <h2>{t("booking.selectService")}</h2>
          {services.data?.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`card ${service?.id === s.id ? "selected" : ""}`}
              onClick={() => {
                setService(s);
                setStep(Math.min(step + 1, steps.length - 1));
              }}
            >
              <div className="card-row">
                <strong>{s.name}</strong>
                <span>
                  {(s.price_cents / 100).toFixed(0)} ₽ · {s.duration_minutes} мин
                </span>
              </div>
            </button>
          ))}
        </>
      )}

      {step === steps.indexOf("specialist") && service && (
        <>
          <h2>{t("booking.selectSpecialist")}</h2>
          <button type="button" className="btn btn-ghost" onClick={() => setAnyStaff(true)}>
            Любой мастер
          </button>
          <div style={{ height: 8 }} />
          {specialists.data?.map((sp) => (
            <button
              key={sp.id}
              type="button"
              className="card"
              onClick={() => {
                setSpecialist(sp);
                setAnyStaff(false);
                setStep(steps.indexOf("time"));
              }}
            >
              {sp.display_name}
            </button>
          ))}
          {anyStaff && (
            <button
              type="button"
              className="btn"
              onClick={() => setStep(steps.indexOf("time"))}
            >
              Далее
            </button>
          )}
        </>
      )}

      {step === steps.indexOf("time") && service && (specialist || anyStaff) && (
        <>
          <h2>Выберите время</h2>
          {slots.isLoading ? (
            <p className="muted">{t("common.loading")}</p>
          ) : (
            <div className="chip-grid">
              {slots.data?.map((sl) => (
                <button
                  key={sl.start}
                  type="button"
                  className={`chip ${slot?.start === sl.start ? "selected" : ""}`}
                  onClick={() => setSlot(sl)}
                >
                  {new Date(sl.start).toLocaleString(undefined, {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </button>
              ))}
            </div>
          )}
          {slot && !bookingId && (
            <button type="button" className="btn" onClick={() => hold.mutate()} disabled={hold.isPending}>
              Забронировать
            </button>
          )}
        </>
      )}

      {step === steps.indexOf("confirm") && service && (
        <div className="card">
          <h2>Сводка</h2>
          <p>{service.name}</p>
          <p className="muted">{selectedStaffName}</p>
          {slot && <p>{new Date(slot.start).toLocaleString()}</p>}
          <p>
            <strong>{(service.price_cents / 100).toFixed(0)} ₽</strong>
          </p>
          {holdExpires && (
            <p className="muted">Удержание до {new Date(holdExpires).toLocaleTimeString()}</p>
          )}
          {bookingId && !confirm.isSuccess && (
            <button type="button" className="btn" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
              {t("booking.confirm")}
            </button>
          )}
          {confirm.isSuccess && <p>Запись подтверждена!</p>}
        </div>
      )}
    </div>
  );
}
