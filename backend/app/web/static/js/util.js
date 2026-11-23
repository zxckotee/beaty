// Tiny DOM helper: children are always inserted as text nodes (no innerHTML with data).
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') el.className = value;
      else if (key === 'style' && typeof value === 'object') {
        for (const [k, v] of Object.entries(value)) {
          if (k.startsWith('--')) el.style.setProperty(k, v);
          else el.style[k] = v;
        }
      }
      else if (key === 'dataset') Object.assign(el.dataset, value);
      else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
      else if (value === true) el.setAttribute(key, '');
      else el.setAttribute(key, value);
    }
  }
  append(el, children);
  // Native append/replaceChildren would stringify null/false children, so route them through the helpers.
  el.append = (...nodes) => append(el, nodes);
  el.replaceChildren = (...nodes) => append(clear(el), nodes);
  return el;
}

const nativeAppend = Element.prototype.append;
export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    nativeAppend.call(el, child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

const ICONS = {
  calendar: '<path d="M7 3v3M17 3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/>',
  users: '<path d="M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19M10 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 19v-1.5a3.5 3.5 0 0 0-2.6-3.4M15.5 5.2a3 3 0 0 1 0 5.6"/>',
  scissors: '<path d="M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  chevL: '<path d="m15 5-7 7 7 7"/>',
  chevR: '<path d="m9 5 7 7-7 7"/>',
  edit: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4zM13.5 6.5l4 4"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3"/>',
  logout: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z"/>',
  send: '<path d="m21 3-9.5 18-2.5-7.5L1.5 11 21 3zM9 13.5 21 3"/>',
  swap: '<path d="M7 7h12l-3-3M17 17H5l3 3"/>',
  camera: '<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1zM12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  chat: '<path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9l-4 3v-3H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/>',
  vk: '<path d="M4 8h4.2c.3 2.2 1.4 3.9 2.9 5.2C11.2 8.8 13 7 15.5 4H20l-3.4 5c3.1 2.8 4.4 4.7 4.6 5.6h-4.8c-1.2-2.3-2.4-4.2-3.7-5.5l-1.5 5.5H8.5L4 8z"/>',
  telegram: '<path d="M20 4 4 11l5.5 1.8L17 7.5 9.5 15l.3 5.2 3.2-2.8L18 20l2-16z"/>',
  max: '<path d="M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm6 5v2m0 4h.01"/>',
};

const SOCIAL_ICON_KEY = { vk: 'vk', telegram: 'telegram', max: 'max' };

export function socialBrandIcon(preset) {
  const key = SOCIAL_ICON_KEY[preset];
  return key ? icon(key) : null;
}

export function icon(name) {
  const span = document.createElement('span');
  span.className = 'ico';
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
  return span;
}

// ---------- formatting ----------
const moneyFmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });
export const money = (cents) => `${moneyFmt.format((cents || 0) / 100)} ₽`;
export const signedMoney = (cents) => `${cents > 0 ? '+' : cents < 0 ? '−' : ''}${money(Math.abs(cents))}`;

export function duration(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (!h) return `${m} мин`;
  if (!m) return `${h} ч`;
  return `${h} ч ${m} мин`;
}

export const toMin = (hhmm) => {
  const [hh, mm] = hhmm.split(':').map(Number);
  return hh * 60 + mm;
};
export const fromMin = (min) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

const wdFmt = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', timeZone: 'UTC' });
const dayFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' });
const longFmt = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' });
const asDate = (iso) => new Date(`${iso}T12:00:00Z`);
export const weekdayShort = (iso) => wdFmt.format(asDate(iso));
export const dayNumber = (iso) => Number(iso.slice(8, 10));
export const dayLabel = (iso) => dayFmt.format(asDate(iso));
export const longDayLabel = (iso) => longFmt.format(asDate(iso));
export const addDays = (iso, n) => {
  const d = asDate(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export function todayIn(tz) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}
export function nowMinutesIn(tz) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date());
  const get = (t) => Number(parts.find((p) => p.type === t).value);
  return get('hour') * 60 + get('minute');
}

export function plural(n, one, few, many) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}

export function hueFor(text) {
  let hash = 0;
  for (const ch of String(text)) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return 34 + (hash % 22);
}
export const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase();

const CHART_COLOR_FALLBACK = { text: '#ececec', gold: '#B8A06A' };

function chartParsableColor(value) {
  if (!value || value.includes('var(')) return false;
  return /^#([0-9a-f]{3,8})$/i.test(value) || /^rgba?\(/i.test(value);
}

/** Resolve a CSS variable to rgb/rgba for APIs that cannot parse var(...). */
export function cssVarColor(varName, host = document.documentElement) {
  const probe = document.createElement('span');
  probe.style.color = `var(${varName})`;
  probe.setAttribute('aria-hidden', 'true');
  probe.style.position = 'absolute';
  probe.style.pointerEvents = 'none';
  probe.style.visibility = 'hidden';
  host.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  host.removeChild(probe);
  if (chartParsableColor(resolved)) return resolved;
  if (varName === '--text') {
    const body = getComputedStyle(document.body).color;
    if (chartParsableColor(body)) return body;
    return CHART_COLOR_FALLBACK.text;
  }
  if (varName === '--ui-gold') return CHART_COLOR_FALLBACK.gold;
  return CHART_COLOR_FALLBACK.text;
}

/** Colors safe for Lightweight Charts (never CSS variables). */
export function chartPalette() {
  const text = cssVarColor('--text');
  let gold = cssVarColor('--ui-gold');
  if (!chartParsableColor(gold) || gold === CHART_COLOR_FALLBACK.text) gold = CHART_COLOR_FALLBACK.gold;
  return { text, gold };
}

export function rgbaFromRgb(rgb, alpha) {
  const m = rgb.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
  if (!m) return rgb;
  return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${alpha})`;
}

export function brandMark(info) {
  const name = info?.name || 'B';
  const url = info?.avatar_url;
  if (url) {
    const img = h('img', { src: url, alt: name, loading: 'lazy', decoding: 'async' });
    img.addEventListener('error', () => {
      const el = img.closest('.brand-mark');
      if (el) el.replaceChildren(document.createTextNode(name[0].toUpperCase()));
    });
    return h('div', { class: 'brand-mark' }, img);
  }
  return h('div', { class: 'brand-mark' }, name[0].toUpperCase());
}

export function syncHeaderBrand(info) {
  if (!info) return;
  const host = document.querySelector('header .brand');
  if (!host) return;
  const nameEl = host.querySelector('.brand-name');
  const next = brandMark(info);
  const old = host.querySelector('.brand-mark');
  if (old) old.replaceWith(next);
  else host.prepend(next);
  if (nameEl && !host.contains(nameEl)) host.append(nameEl);
}

export function debounce(fn, ms) {
  let t;
  const debounced = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
  debounced.cancel = () => clearTimeout(t);
  return debounced;
}
