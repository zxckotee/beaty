/** Telegram + MAX Mini App helpers. */

import { isTelegramWebApp, prepareTelegramChrome, telegramInitData } from './telegram.js';

export function detectChannel() {
  if (isTelegramWebApp()) return 'telegram';
  const w = window.WebApp;
  if (w && w.initData) return 'max';
  return null;
}

export function initData() {
  const channel = detectChannel();
  if (channel === 'telegram') return telegramInitData();
  const w = window.WebApp;
  return w && w.initData ? w.initData : '';
}

export function prepareChrome() {
  const channel = detectChannel();
  if (channel === 'telegram') {
    prepareTelegramChrome();
    return;
  }
  const w = window.WebApp;
  if (!w) return;
  try {
    if (w.ready) w.ready();
    if (w.expand) w.expand();
  } catch {
    /* ignore */
  }
}

export function isMessengerWebApp() {
  return Boolean(detectChannel());
}

export { isTelegramWebApp, telegramInitData, prepareTelegramChrome };