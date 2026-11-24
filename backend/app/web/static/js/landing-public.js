function tenantFromPath() {
  const m = location.pathname.match(/\/t\/([^/]+)\/studio/);
  return m ? m[1] : null;
}

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (v != null) node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null) continue;
    node.append(typeof kid === 'string' ? document.createTextNode(kid) : kid);
  }
  return node;
}

function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();
}

import { renderProfileWidget } from './profile-widgets.js';
import { applyTheme, resolveInitialTheme, themeToggleButton } from './theme.js';

function bookUrl(tenantId, botUsername) {
  if (botUsername) return `https://t.me/${botUsername}?start=book`;
  return `/t/${tenantId}/#/book`;
}

function mapPointsFromData(data) {
  const pts = [];
  for (const loc of data.dgis_locations || []) {
    if (loc.map_lat != null && loc.map_lon != null) {
      pts.push({ lat: Number(loc.map_lat), lon: Number(loc.map_lon), label: loc.label || '' });
    }
  }
  if (!pts.length && data.map_lat != null && data.map_lon != null) {
    pts.push({ lat: Number(data.map_lat), lon: Number(data.map_lon), label: data.title || '' });
  }
  return pts;
}

function initMapFromPoints(data) {
  const pts = mapPointsFromData(data);
  const mapEl = document.getElementById('studio-map');
  if (!mapEl || !window.L || !pts.length) return;
  const map = L.map(mapEl, { scrollWheelZoom: false });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map);
  const markers = [];
  for (const p of pts) {
    const m = L.marker([p.lat, p.lon]).addTo(map);
    if (p.label) m.bindPopup(p.label);
    markers.push(m);
  }
  if (pts.length === 1) {
    map.setView([pts[0].lat, pts[0].lon], data.map_zoom || 17);
  } else {
    map.fitBounds(L.featureGroup(markers).getBounds().pad(0.12));
  }
  setTimeout(() => map.invalidateSize(), 200);
}

function initFloors(complexId, firmId) {
  const host = document.getElementById('studio-floors');
  if (!host || !complexId || !firmId || !window.DG) return;
  window.DG.FloorsWidget.init({
    container: host,
    width: '100%',
    height: '100%',
    initData: {
      complexId: String(complexId),
      options: { initialFirm: String(firmId), locale: 'ru_RU' },
    },
  });
}

function loadFloorsScript(complexId, firmId) {
  if (!complexId || !firmId) return;
  const s = document.createElement('script');
  s.charset = 'utf-8';
  s.src = 'https://floors-widget.api.2gis.ru/loader.js';
  s.onload = () => initFloors(complexId, firmId);
  document.body.appendChild(s);
}

function render(data, tenantId) {
  const root = document.getElementById('studio-root');
  root.replaceChildren();
  const wrap = el('div', { class: 'studio' });

  const hero = el('header', { class: 'studio-hero' });
  const cover = el('div', {
    class: 'studio-cover',
    style: data.cover_url ? `background-image:url(${data.cover_url})` : '',
  });
  hero.append(cover);
  const body = el('div', { class: 'studio-hero-body' });
  if (data.avatar_url) {
    body.append(el('img', { class: 'studio-avatar', src: data.avatar_url, alt: data.title || '' }));
  } else {
    body.append(el('div', { class: 'studio-avatar studio-avatar-fallback' }, initials(data.title)));
  }
  body.append(el('h1', { class: 'studio-title' }, data.title || 'Салон'));
  if (data.tagline) body.append(el('p', { class: 'studio-tagline' }, data.tagline));
  hero.append(body);
  wrap.append(hero);

  const widgets = (data.widgets || []).filter((w) => w.is_visible).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
  if (widgets.length) {
    const wzone = el('div', { class: 'studio-widgets' });
    const bookHref = bookUrl(tenantId, data.bot_username);
    for (const w of widgets) {
      wzone.append(renderProfileWidget(w, { mode: 'studio', bookHref }));
    }
    wrap.append(wzone);
  }

  const portfolio = data.portfolio || [];
  if (portfolio.length) {
    const sec = el('section', { class: 'studio-section' });
    sec.append(el('h2', null, 'Наши работы'));
    const grid = el('div', { class: 'portfolio-grid' });
    for (const item of portfolio) {
      const card = el('article', { class: 'portfolio-card' });
      const photos = item.photo_urls || [];
      if (photos[0]) card.append(el('img', { src: photos[0], alt: item.title, loading: 'lazy' }));
      const b = el('div', { class: 'body' });
      b.append(el('h3', null, item.title));
      if (item.description) b.append(el('p', null, item.description));
      card.append(b);
      grid.append(card);
    }
    sec.append(grid);
    wrap.append(sec);
  }

  const hasDgisMap = data.dgis_embed_src || (data.dgis_locations && data.dgis_locations.length) || data.dgis_embed_html;
  if (hasDgisMap || data.dgis_url || (data.map_lat != null && data.map_lon != null)) {
    const sec = el('section', { class: 'studio-section' });
    sec.append(el('h2', null, 'Как нас найти'));
    if (!hasDgisMap && mapPointsFromData(data).length) {
      sec.append(el('div', { class: 'map-wrap' }, el('div', { id: 'studio-map' })));
    }
    const actions = el('div', { class: 'map-actions' });
    const locs =
      (data.dgis_locations && data.dgis_locations.length)
        ? data.dgis_locations
        : data.dgis_url
          ? [{ dgis_url: data.dgis_url, label: null }]
          : [];
    for (const loc of locs) {
      if (loc.dgis_url) {
        actions.append(
          el('a', {
            class: locs.length === 1 ? 'primary' : '',
            href: loc.dgis_url,
            target: '_blank',
            rel: 'noopener',
          }, loc.label || 'Открыть в 2ГИС'),
        );
      }
    }
    actions.append(el('a', { href: bookUrl(tenantId, data.bot_username) }, 'Онлайн-запись'));
    sec.append(actions);
    if (data.dgis_embed_src) {
      const embedWrap = el('div', { class: 'dgis-embed' });
      embedWrap.append(
        el('iframe', {
          src: data.dgis_embed_src,
          title: 'Карта 2ГИС',
          loading: 'lazy',
          style: 'border:0;width:100%;height:100%;min-height:320px',
        }),
      );
      sec.append(embedWrap);
    } else if (data.dgis_embed_html) {
      sec.append(el('div', { class: 'dgis-embed', html: data.dgis_embed_html }));
    }
    if (data.dgis_complex_id && data.dgis_firm_id) {
      sec.append(el('div', { id: 'studio-floors', class: 'floors-wrap' }));
    }
    wrap.append(sec);
  }

  const posts = (data.posts || []).filter((p) => p.body || (p.photo_urls || []).length);
  if (posts.length) {
    const sec = el('section', { class: 'studio-section' });
    sec.append(el('h2', null, 'Новости'));
    for (const post of posts) {
      const card = el('article', { class: 'post-card' });
      if (post.title) card.append(el('h3', null, post.title));
      if (post.body) card.append(el('div', { class: 'post-body' }, post.body));
      const ph = post.photo_urls || [];
      if (ph.length) {
        const row = el('div', { class: 'post-photos' });
        for (const url of ph) row.append(el('img', { src: url, alt: '', loading: 'lazy' }));
        card.append(row);
      }
      sec.append(card);
    }
    wrap.append(sec);
  }

  root.append(wrap);

  const usedDgisEmbed = Boolean(data.dgis_embed_src || data.dgis_embed_html);
  if (!usedDgisEmbed && mapPointsFromData(data).length) {
    initMapFromPoints(data);
  }
  loadFloorsScript(data.dgis_complex_id, data.dgis_firm_id);
}

function mountStudioChrome() {
  applyTheme(resolveInitialTheme());
  const fab = themeToggleButton();
  fab.className = 'studio-theme-fab theme-toggle';
  document.body.append(fab);
}

async function main() {
  mountStudioChrome();
  const tenantId = tenantFromPath();
  const root = document.getElementById('studio-root');
  if (!tenantId) {
    root.append(el('div', { class: 'studio-error' }, 'Не найден салон'));
    return;
  }
  try {
    const res = await fetch(`/api/t/${tenantId}/landing`);
    if (!res.ok) throw new Error('not found');
    const data = await res.json();
    document.title = `${data.title || 'Салон'} · студия`;
    render(data, tenantId);
  } catch {
    root.append(el('div', { class: 'studio-error' }, 'Страница ещё не опубликована или недоступна.'));
  }
}

main();