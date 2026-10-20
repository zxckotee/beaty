import { useQuery } from "@tanstack/react-query";
import { fetchMyBookings } from "../api/client";

type Props = { tenantPublicId: string };

export function MyBookingsPage({ tenantPublicId }: Props) {
  const q = useQuery({
    queryKey: ["my-bookings", tenantPublicId],
    queryFn: () => fetchMyBookings(tenantPublicId),
  });
  if (q.isLoading) return <p>Загрузка…</p>;
  return (
    <ul>
      {q.data?.map((b) => (
        <li key={b.id}>
          {b.id.slice(0, 8)}… — {b.status} — {(b.total_price_cents / 100).toFixed(0)} ₽
        </li>
      ))}
    </ul>
  );
}
