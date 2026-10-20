import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Route, Routes, useParams } from "react-router-dom";
import { authTelegram, setAccessToken } from "./api/client";
import "./App.css";
import { ClientBookingPage } from "./pages/ClientBookingPage";
import { ManagerPage } from "./pages/ManagerPage";
import { MyBookingsPage } from "./pages/MyBookingsPage";
import { StaffDayPage } from "./pages/StaffDayPage";

const queryClient = new QueryClient();

function TenantShell() {
  const { tenantPublicId = "demo" } = useParams();
  const { t } = useTranslation();
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) return;
    authTelegram(tenantPublicId, initData)
      .then((res) => setAccessToken(res.access_token))
      .catch((e: Error) => setAuthError(e.message));
  }, [tenantPublicId]);

  const nav = useMemo(
    () => (
      <nav className="nav">
        <Link to={`/t/${tenantPublicId}/book`}>{t("nav.book")}</Link>
        <Link to={`/t/${tenantPublicId}/my`}>{t("nav.my")}</Link>
        <Link to={`/t/${tenantPublicId}/manager`}>{t("nav.manager")}</Link>
        <Link to={`/t/${tenantPublicId}/staff`}>{t("nav.staff")}</Link>
      </nav>
    ),
    [tenantPublicId, t],
  );

  return (
    <div className="shell">
      <header>
        <h1>{t("app.title")}</h1>
        {nav}
      </header>
      {authError && <p className="error">Auth: {authError}</p>}
      <Routes>
        <Route path="book" element={<ClientBookingPage tenantPublicId={tenantPublicId} />} />
        <Route path="my" element={<MyBookingsPage tenantPublicId={tenantPublicId} />} />
        <Route path="manager" element={<ManagerPage />} />
        <Route path="staff" element={<StaffDayPage />} />
        <Route path="*" element={<ClientBookingPage tenantPublicId={tenantPublicId} />} />
      </Routes>
    </div>
  );
}

declare global {
  interface Window {
    Telegram?: { WebApp?: { initData?: string; ready?: () => void } };
  }
}

export default function App() {
  useEffect(() => {
    window.Telegram?.WebApp?.ready?.();
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
