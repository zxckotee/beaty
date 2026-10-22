import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { authTelegram, fetchTenantBrand, setAccessToken } from "./api/client";
import { ClientBookingPage } from "./client/ClientBookingPage";
import { MyBookingsPage } from "./client/MyBookingsPage";
import { ManagerPage } from "./manager/ManagerPage";
import { StaffDayPage } from "./staff/StaffDayPage";
import { isManager, isStaff, useMe } from "./shared/useMe";
import "./shared/theme.css";

const queryClient = new QueryClient();

function TenantShell() {
  const { tenantPublicId = "demo" } = useParams();
  const { t } = useTranslation();
  const me = useMe(tenantPublicId);

  useEffect(() => {
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) return;
    authTelegram(tenantPublicId, initData)
      .then((res) => {
        setAccessToken(res.access_token);
        me.refetch();
      })
      .catch(() => undefined);
  }, [tenantPublicId]);

  useEffect(() => {
    fetchTenantBrand(tenantPublicId)
      .then((b) => {
        const primary = b.brand?.primary as string | undefined;
        if (primary) document.documentElement.style.setProperty("--beaty-brand", primary);
      })
      .catch(() => undefined);
  }, [tenantPublicId]);

  const roles = me.data?.roles ?? ["client"];
  const nav = useMemo(
    () => (
      <nav className="nav-tabs">
        <NavLink to={`/t/${tenantPublicId}/book`} className={({ isActive }) => (isActive ? "active" : "")}>
          {t("nav.book")}
        </NavLink>
        <NavLink to={`/t/${tenantPublicId}/my`} className={({ isActive }) => (isActive ? "active" : "")}>
          {t("nav.my")}
        </NavLink>
        {isManager(roles) && (
          <NavLink to={`/t/${tenantPublicId}/manager`} className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.manager")}
          </NavLink>
        )}
        {isStaff(roles) && (
          <NavLink to={`/t/${tenantPublicId}/staff`} className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.staff")}
          </NavLink>
        )}
      </nav>
    ),
    [tenantPublicId, t, roles],
  );

  return (
    <div className="shell">
      <header className="shell-header">
        <h1 className="shell-title">{me.data?.tenant_name ?? t("app.title")}</h1>
        {me.data?.subscription_status === "expired" && (
          <p className="error">Подписка неактивна — доступ только для просмотра</p>
        )}
        {nav}
      </header>
      <Routes>
        <Route path="book" element={<ClientBookingPage tenantPublicId={tenantPublicId} />} />
        <Route path="my" element={<MyBookingsPage tenantPublicId={tenantPublicId} />} />
        <Route path="manager" element={<ManagerPage tenantPublicId={tenantPublicId} />} />
        <Route path="staff" element={<StaffDayPage tenantPublicId={tenantPublicId} />} />
        <Route path="*" element={<ClientBookingPage tenantPublicId={tenantPublicId} />} />
      </Routes>
    </div>
  );
}

declare global {
  interface Window {
    Telegram?: { WebApp?: { initData?: string; ready?: () => void; themeParams?: Record<string, string> } };
  }
}

export default function App() {
  useEffect(() => {
    window.Telegram?.WebApp?.ready?.();
    const tp = window.Telegram?.WebApp?.themeParams;
    if (tp) {
      Object.entries(tp).forEach(([k, v]) => {
        document.documentElement.style.setProperty(`--tg-theme-${k.replace(/_/g, "-")}`, v);
      });
    }
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route path="/t/:tenantPublicId/*" element={<TenantShell />} />
        <Route path="*" element={<TenantShell />} />
      </Routes>
    </QueryClientProvider>
  );
}
