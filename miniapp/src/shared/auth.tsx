import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authTelegram, getAccessToken, setAccessToken } from "../api/client";

export type AuthStatus = "no-telegram" | "authenticating" | "ready" | "failed";

type AuthContextValue = {
  status: AuthStatus;
  token: string | null;
  retryAuth: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  tenantPublicId,
  children,
}: {
  tenantPublicId: string;
  children: ReactNode;
}) {
  const [status, setStatus] = useState<AuthStatus>("authenticating");
  const [token, setToken] = useState<string | null>(() => getAccessToken());
  const [attempt, setAttempt] = useState(0);

  const runAuth = useCallback(() => {
    const initData = window.Telegram?.WebApp?.initData?.trim();
    if (!initData) {
      setStatus("no-telegram");
      setToken(null);
      setAccessToken(null);
      return;
    }
    setStatus("authenticating");
    authTelegram(tenantPublicId, initData)
      .then((res) => {
        setAccessToken(res.access_token);
        setToken(res.access_token);
        setStatus("ready");
      })
      .catch(() => {
        setAccessToken(null);
        setToken(null);
        setStatus("failed");
      });
  }, [tenantPublicId]);

  useEffect(() => {
    runAuth();
  }, [runAuth, attempt]);

  const value = useMemo(
    () => ({
      status,
      token,
      retryAuth: () => setAttempt((n) => n + 1),
    }),
    [status, token],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth requires AuthProvider");
  return ctx;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { status, retryAuth } = useAuth();

  if (status === "no-telegram") {
    return (
      <div className="page auth-gate">
        <h2>Нужен Telegram</h2>
        <p className="muted">
          Mini App работает внутри Telegram: откройте ссылку из бота салона (кнопка «Запись» или меню).
          В обычном браузере по IP вход недоступен — нет подписи Telegram.
        </p>
      </div>
    );
  }

  if (status === "authenticating") {
    return (
      <div className="page">
        <p className="muted">Вход через Telegram…</p>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="page auth-gate">
        <h2>Не удалось войти</h2>
        <p className="muted">Проверьте, что салон существует и вы открыли актуальную ссылку из бота.</p>
        <button type="button" className="btn" onClick={retryAuth}>
          Повторить
        </button>
      </div>
    );
  }

  return <>{children}</>;
}
