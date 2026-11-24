import { icon } from './util.js';

export const THEME_KEY = 'beaty.theme';

export function resolveInitialTheme() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    /* private mode */
  }
  return 'dark';
}

export function applyTheme(theme) {
  const next = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch {
    /* private mode */
  }
  const themeColor = next === 'light' ? '#ececec' : '#000000';
  let metaTheme = document.querySelector('meta[name="theme-color"]');
  if (!metaTheme) {
    metaTheme = document.createElement('meta');
    metaTheme.name = 'theme-color';
    document.head.appendChild(metaTheme);
  }
  metaTheme.setAttribute('content', themeColor);
  let metaScheme = document.querySelector('meta[name="color-scheme"]');
  if (!metaScheme) {
    metaScheme = document.createElement('meta');
    metaScheme.name = 'color-scheme';
    document.head.appendChild(metaScheme);
  }
  metaScheme.setAttribute('content', next);
  window.dispatchEvent(new CustomEvent('beaty-theme', { detail: { theme: next } }));
}

export function getTheme() {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

export function toggleTheme() {
  const next = getTheme() === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  return next;
}

function syncThemeToggle(btn) {
  const dark = getTheme() === 'dark';
  btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
  btn.title = dark ? 'Светлая тема' : 'Тёмная тема';
  btn.setAttribute('aria-label', btn.title);
  const ico = btn.querySelector('.ico');
  if (ico) {
    const path = dark ? iconMoonPath() : iconSunPath();
    ico.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  }
}

function iconSunPath() {
  return '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>';
}

function iconMoonPath() {
  return '<path d="M21 14.5A8.5 8.5 0 0 1 9.5 3 7 7 0 1 0 21 14.5z"/>';
}

/** @returns {HTMLButtonElement} */
export function themeToggleButton() {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn ghost icon-btn theme-toggle';
  btn.append(icon('sun'));
  syncThemeToggle(btn);
  btn.addEventListener('click', () => {
    toggleTheme();
    document.querySelectorAll('.theme-toggle').forEach((el) => syncThemeToggle(el));
  });
  window.addEventListener('beaty-theme', () => syncThemeToggle(btn));
  return btn;
}