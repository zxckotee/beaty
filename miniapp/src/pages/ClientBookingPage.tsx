import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  confirmBooking,
  fetchServices,
  fetchSpecialists,
  holdBooking,
  type Service,
  type Specialist,
} from "../api/client";

type Props = { tenantPublicId: string };

export function ClientBookingPage({ tenantPublicId }: Props) {
  const { t } = useTranslation();
  const [service, setService] = useState<Service | null>(null);
  const [specialist, setSpecialist] = useState<Specialist | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(null);

  const services = useQuery({
    queryKey: ["services", tenantPublicId],
    queryFn: () => fetchServices(tenantPublicId),
  });
  const specialists = useQuery({
    queryKey: ["specialists", tenantPublicId],
    queryFn: () => fetchSpecialists(tenantPublicId),
    enabled: !!service,
  });

  const hold = useMutation({
    mutationFn: () =>
      holdBooking(tenantPublicId, {
        staff_member_id: specialist!.id,
        service_id: service!.id,
        start_at: new Date(Date.now() + 86400000).toISOString(),
      }),
    onSuccess: (b) => setBookingId(b.id),
  });

  const confirm = useMutation({
    mutationFn: () => confirmBooking(tenantPublicId, bookingId!),
  });

  if (services.isLoading) return <p>{t("common.loading")}</p>;
  if (services.error) return <p>{t("common.error")}</p>;

  return (
    <div className="page">
      <h2>{t("booking.selectService")}</h2>
      <ul>
        {services.data?.map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => setService(s)}>
              {s.name} — {(s.price_cents / 100).toFixed(0)} ₽, {s.duration_minutes} мин
            </button>
          </li>
        ))}
      </ul>

      {service && (
        <>
          <h2>{t("booking.selectSpecialist")}</h2>
          {specialists.isLoading ? (
            <p>{t("common.loading")}</p>
          ) : (
            <ul>
              {specialists.data?.map((sp) => (
                <li key={sp.id}>
                  <button type="button" onClick={() => setSpecialist(sp)}>
                    {sp.display_name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {service && specialist && !bookingId && (
        <button type="button" onClick={() => hold.mutate()} disabled={hold.isPending}>
          Забронировать слот (завтра)
        </button>
      )}

      {bookingId && (
        <button type="button" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
          {t("booking.confirm")}
        </button>
      )}

      {confirm.isSuccess && <p>Запись подтверждена!</p>}
    </div>
  );
}
