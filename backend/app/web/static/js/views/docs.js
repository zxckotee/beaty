import { api, friendly } from '../api.js';
import { h } from '../util.js';
import { isManager, store } from '../store.js';
import { spinner } from '../ui.js';

const CLIENT_OPEN = new Set(['client-booking', 'client-mine']);
const MANAGER_OPEN = new Set(['mgr-dashboard', 'mgr-team']);

function sectionContent(s) {
  const bodyParts = [];
  if (Array.isArray(s.paragraphs) && s.paragraphs.length) {
    for (const text of s.paragraphs) bodyParts.push(h('p', null, text));
  } else if (s.body) {
    bodyParts.push(h('p', null, s.body));
  }
  if (Array.isArray(s.bullets) && s.bullets.length) {
    bodyParts.push(h('ul', { class: 'docs-bullets' }, ...s.bullets.map((text) => h('li', null, text))));
  }
  if (bodyParts.length) return h('div', { class: 'docs-details-body' }, ...bodyParts);
  return h('div', { class: 'docs-details-body' }, h('p', null, s.body || ''));
}

function sectionDetails(s, open) {
  return h('details', { class: 'docs-details', open: open || undefined }, h('summary', null, s.title), sectionContent(s));
}

function defaultOpen(section, isMgr) {
  const id = section.id || '';
  if (isMgr && section.audience === 'manager') return MANAGER_OPEN.has(id);
  if (section.audience === 'client') return CLIENT_OPEN.has(id);
  return false;
}

function groupedSections(sections, isMgr) {
  if (!isMgr) {
    return [{ label: 'Справка для клиента', items: sections }];
  }
  const client = sections.filter((s) => s.audience === 'client');
  const mgr = sections.filter((s) => s.audience === 'manager');
  const groups = [];
  if (client.length) groups.push({ label: 'Для клиентов', items: client });
  if (mgr.length) groups.push({ label: 'Для управляющего и мастеров', items: mgr });
  return groups;
}

export async function docsView() {
  const root = h('div', { class: 'docs-view' });
  root.append(spinner());

  try {
    const data = await api.get('/docs');
    const isMgr = isManager();
    const salonName = store.info ? store.info.name : '';
    root.replaceChildren();

    const hero = h('header', { class: 'docs-hero' }, h('h1', null, 'Документация'), h('p', { class: 'docs-hero-lead' }, salonName));
    if (isMgr) {
      hero.append(
        h(
          'p',
          { class: 'docs-hero-note' },
          'Подсказки для команды салона и ответы, которые видят ваши клиенты в боте.',
        ),
      );
    } else {
      hero.append(h('p', { class: 'docs-hero-note' }, 'Как записаться, управлять визитами и оставить отзыв.'));
    }
    root.append(hero);

    for (const group of groupedSections(data.sections || [], isMgr)) {
      const block = h('section', { class: 'docs-group' }, h('h2', { class: 'docs-group-title' }, group.label));
      const list = h('div', { class: 'docs-sections' });
      for (const s of group.items) {
        list.append(sectionDetails(s, defaultOpen(s, isMgr)));
      }
      block.append(list);
      root.append(block);
    }

    if (data.legal_links?.length) {
      const legal = h(
        'section',
        { class: 'docs-legal-card' },
        h('h2', { class: 'docs-group-title' }, 'Правовые материалы'),
        h(
          'ul',
          { class: 'docs-legal-links' },
          ...data.legal_links.map((l) =>
            h('li', null, h('a', { href: l.href, target: '_blank', rel: 'noopener' }, l.label)),
          ),
        ),
      );
      root.append(legal);
    }

    root.append(h('p', { class: 'docs-footer-hint' }, 'В Telegram-боте — кнопка «Справка» с тем же содержанием.'));
  } catch (e) {
    root.replaceChildren(h('div', { class: 'docs-hero docs-hero--error' }, h('p', null, friendly(e))));
  }
  return root;
}