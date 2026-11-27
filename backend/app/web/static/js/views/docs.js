import { api, friendly } from '../api.js';
import { h, icon } from '../util.js';
import { isManager, store } from '../store.js';
import { spinner } from '../ui.js';

export async function docsView() {
  const root = h('div', { class: 'docs-view' });
  const body = h('div', { class: 'card pad' });
  root.append(body, spinner());

  try {
    const data = await api.get('/docs');
    body.replaceChildren(h('h1', null, 'Документация'), h('p', { class: 'muted' }, store.info ? store.info.name : ''));
    const list = h('div', { class: 'docs-sections' });
    for (const s of data.sections || []) {
      const bodyParts = [];
      if (Array.isArray(s.paragraphs) && s.paragraphs.length) {
        for (const text of s.paragraphs) bodyParts.push(h('p', null, text));
      } else if (s.body) {
        bodyParts.push(h('p', null, s.body));
      }
      if (Array.isArray(s.bullets) && s.bullets.length) {
        bodyParts.push(h('ul', { class: 'docs-bullets' }, ...s.bullets.map((text) => h('li', null, text))));
      }
      const content = bodyParts.length ? h('div', { class: 'docs-details-body' }, ...bodyParts) : h('p', null, s.body || '');
      const det = h(
        'details',
        { class: 'docs-details', open: isManager() && s.id === 'mgr-dashboard' },
        h('summary', null, s.title),
        content,
      );
      list.append(det);
    }
  body.append(list);
    if (data.legal_links?.length) {
      const legal = h('section', { class: 'docs-legal' }, h('h2', null, 'Правовые материалы'), h('ul', null, ...data.legal_links.map((l) => h('li', null, h('a', { href: l.href, target: '_blank', rel: 'noopener' }, l.label)))));
      body.append(legal);
    }
    const hint = h('p', { class: 'tiny muted' }, 'В Telegram-боте салона — кнопка «Справка» с тем же содержанием.');
    body.append(hint);
  } catch (e) {
    body.replaceChildren(h('p', null, friendly(e)));
  }
  return root;
}