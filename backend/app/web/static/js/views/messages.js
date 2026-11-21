import { api, friendly } from '../api.js';
import { h } from '../util.js';
import { field, photoPicker, spinner, toast, withBusy } from '../ui.js';

const KIND_LABELS = {
  booking_confirmed: 'Подтверждение записи',
  reminder_24h: 'Напоминание за 24 ч',
  reminder_2h: 'Напоминание за 2 ч',
  booking_cancelled: 'Отмена записи',
};

export async function messagesView() {
  const root = h('div');
  const panel = h('div');
  let meta = null;
  let templates = {};
  let activeKind = 'booking_confirmed';

  root.append(
    h('div', { class: 'page-head' }, h('div', null, h('h1', null, 'Сообщения бота'), h('p', { class: 'muted' }, 'Шаблоны с токенами и фото для Telegram.'))),
    h('div', { class: 'chips', id: 'msg-tabs' }),
    panel,
  );
  panel.append(spinner());

  function insertToken(token) {
    const ta = panel.querySelector('#msg-body');
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const text = ta.value;
    ta.value = text.slice(0, start) + `{${token}}` + text.slice(end);
    ta.focus();
  }

  async function reload() {
    meta = await api.get('/manager/messages/meta');
    const res = await api.get('/manager/messages');
    templates = res.templates;
    drawTabs();
    drawEditor();
  }

  function drawTabs() {
    const tabs = root.querySelector('#msg-tabs');
  tabs.replaceChildren(
      ...Object.keys(KIND_LABELS).map((kind) =>
        h(
          'button',
          {
            class: `chip${kind === activeKind ? ' active' : ''}`,
            type: 'button',
            onclick: () => {
              activeKind = kind;
              drawTabs();
              drawEditor();
            },
          },
          KIND_LABELS[kind],
        ),
      ),
    );
  }

  function drawEditor() {
    const tpl = templates[activeKind] || { body: '', photo_slots: [], parse_mode: 'HTML' };
    const body = h('textarea', { class: 'textarea', id: 'msg-body', rows: '12', placeholder: 'Текст с HTML и эмодзи' }, tpl.body || '');
    const preview = h('pre', { class: 'card small', style: { whiteSpace: 'pre-wrap' }, id: 'msg-preview' }, '—');
    const chips = h(
      'div',
      { class: 'chips' },
      ...(meta.tokens || []).map(([key, label]) =>
        h('button', { class: 'chip', type: 'button', onclick: () => insertToken(key), title: label }, `{${key}}`),
      ),
    );
    const staffPhoto = h('label', { class: 'row' }, h('input', { type: 'checkbox', class: 'check', checked: slotHas(tpl, 'staff') }), 'Фото мастера');
    const coverPhoto = h('label', { class: 'row' }, h('input', { type: 'checkbox', class: 'check', checked: slotHas(tpl, 'venue_cover') }), 'Обложка лендинга');
    const custom = photoPicker({ url: customUrl(tpl), name: 'Фото', square: true });
    let customUrlStored = customUrl(tpl);

    const previewBtn = h('button', { class: 'btn sm', type: 'button' }, 'Превью');
    previewBtn.addEventListener('click', async () => {
      try {
        const res = await api.post('/manager/messages/preview', { kind: activeKind, body: body.value });
        preview.textContent = res.text;
      } catch (e) {
        toast(friendly(e), true);
      }
    });

    const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить шаблон');
    save.addEventListener('click', () =>
      withBusy(save, async () => {
        try {
          const slots = [];
          if (staffPhoto.querySelector('input').checked) slots.push('staff');
          if (coverPhoto.querySelector('input').checked) slots.push('venue_cover');
          const file = custom.getFile();
          if (file) {
            const up = await api.upload('/manager/messages/photo', file);
            slots.push({ type: 'custom', url: up.url });
            customUrlStored = up.url;
          } else if (customUrlStored) {
            slots.push({ type: 'custom', url: customUrlStored });
          }
          await api.put(`/manager/messages/${activeKind}`, {
            body: body.value,
            parse_mode: 'HTML',
            photo_slots: slots,
          });
          toast('Шаблон сохранён');
          await reload();
        } catch (e) {
          toast(friendly(e), true);
        }
      }),
    );

    panel.replaceChildren(
      field('Текст', body, 'HTML: <b>, <i>, <a href="...">. Токены — кнопками ниже.'),
      chips,
      staffPhoto,
      coverPhoto,
      custom.el,
      h('div', { class: 'row', style: { gap: '8px' } }, previewBtn, save),
      h('h3', null, 'Пример подстановки'),
      preview,
    );
  }

  function slotHas(tpl, name) {
    return (tpl.photo_slots || []).some((s) => s === name || (s && s.type === name));
  }

  function customUrl(tpl) {
    const c = (tpl.photo_slots || []).find((s) => s && s.type === 'custom');
    return c && c.url ? c.url : null;
  }

  try {
    await reload();
  } catch (e) {
    panel.replaceChildren(h('p', null, friendly(e)));
  }
  return root;
}