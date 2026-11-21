/** Telegram Mini App helpers (browser + WebView). */

export function isTelegramWebApp() {
  const tg = window.Telegram && window.Telegram.WebApp;
  return Boolean(tg && tg.initData);
}

export function telegramInitData() {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) return '';
  return tg.initData || '';
}

export function prepareTelegramChrome() {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
  } catch {
    /* ignore */
  }
}