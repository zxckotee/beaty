import { useQuery } from "@tanstack/react-query";
import { fetchMe, type MeResponse } from "../api/client";

export function useMe(tenantPublicId: string) {
  return useQuery<MeResponse>({
    queryKey: ["me", tenantPublicId],
    queryFn: () => fetchMe(tenantPublicId),
    retry: 1,
  });
}

export function isStaff(roles: string[]) {
  return roles.some((r) => ["owner", "manager", "reception", "specialist"].includes(r));
}

export function isManager(roles: string[]) {
  return roles.some((r) => ["owner", "manager", "reception"].includes(r));
}
