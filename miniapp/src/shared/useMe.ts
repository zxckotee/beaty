import { useQuery } from "@tanstack/react-query";
import { fetchMe, type MeResponse } from "../api/client";
import { useAuth } from "./auth";

export function useMe(tenantPublicId: string) {
  const { status } = useAuth();
  return useQuery<MeResponse>({
    queryKey: ["me", tenantPublicId],
    queryFn: () => fetchMe(tenantPublicId),
    enabled: status === "ready",
  });
}

export function isStaff(roles: string[]) {
  return roles.some((r) => ["owner", "manager", "reception", "specialist"].includes(r));
}

export function isManager(roles: string[]) {
  return roles.some((r) => ["owner", "manager", "reception"].includes(r));
}
