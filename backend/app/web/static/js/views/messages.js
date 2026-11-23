import { api, friendly } from '../api.js';
import { isTelegramWebApp } from '../telegram.js';
import { debounce, h, icon } from '../util.js';
import { field, photoPicker, spinner, toast, withBusy } from '../ui.js';
import { createTokenEditor } from '../token-editor.js';

const KIND_LABELS = {
  booking_confirmed: 'Подтверждение',
  reminder_24h: 'За 24 часа',
  reminder_2h: 'За 2 часа',
  booking_cancelled: 'Отмена',
};

const KIND_HINTS = {
  booking_confirmed: 'Клиенту сразу после успешной записи.',
  reminder_24h: 'Автоматически за сутки до визита.',
  reminder_2h: 'Автоматически за 2 часа до визита.',
  booking_cancelled: 'Когда запись отменена салоном или клиентом.',
};

export async function messagesView({ embedded = false } = {}) {
  const root = h('section', {
    class: `messages-page${embedded ? ' messages-page--embedded dash-section' : ' dash-section-standalone'}`,
    ...(embedded ? { id: 'dash-messages' } : {}),
  });
  const titleTag = embedded ? 'h2' : 'h1';
  const panel = h('div', { class: 'messages-panel' });
  let meta = null;
  let templates = {};
  let activeKind = 'booking_confirmed';
  let previewEl = null;
  /** @type {ReturnType<typeof createTokenEditor> | null} */
  let editor = null;
  const tgWebApp = isTelegramWebApp();

  root.append(
    h(
      'div',
      { class: 'page-head' },
      h(
        'div',
        null,
        h(titleTag, null, 'Напоминания в Telegram'),
        h('p', { class: 'muted' }, 'Шаблоны напоминаний с переменными, HTML и вложениями для бота.'),
      ),
    ),
    h('nav', { class: 'chips scroll messages-kinds', id: 'msg-tabs', 'aria-label': 'Тип напоминания' }),
    panel,
  );
  panel.append(spinner());

  const runPreview = debounce(async () => {
    if (!editor || !previewEl) return;
    try {
      const res = await api.post('/manager/messages/preview', {
        kind: activeKind,
        body: editor.getBody(),
      });
      previewEl.textContent = res.text || '—';
      previewEl.classList.remove('msg-preview-empty');
    } catch {
      previewEl.textContent = 'Не удалось построить превью';
      previewEl.classList.add('msg-preview-empty');
    }
  }, 500);

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

  function schedulePreview() {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => runPreview());
    });
  }

  function drawEditor() {
    runPreview.cancel();
    const tpl = templates[activeKind] || { body: '', photo_slots: [], parse_mode: 'HTML' };

    editor = createTokenEditor({
      body: tpl.body || '',
      tokens: meta?.tokens || [],
      onInput: tgWebApp ? undefined : () => schedulePreview(),
    });

    previewEl = h('div', { class: 'msg-preview-body msg-preview-empty' }, 'Нажмите «Обновить превью» или начните вводить текст');

    const tokenChips = h(
      'div',
      { class: 'chips messages-tokens' },
      ...(meta?.tokens || []).map(([key, label]) =>
        h(
          'button',
          { class: 'chip', type: 'button', onclick: () => editor.insertToken(key), title: `Вставить: ${label}` },
          label,
        ),
      ),
    );

    const staffPhoto = h('input', { type: 'checkbox', class: 'check', checked: slotHas(tpl, 'staff') });
    const coverPhoto = h('input', { type: 'checkbox', class: 'check', checked: slotHas(tpl, 'venue_cover') });
    const custom = photoPicker({ url: customUrl(tpl), name: 'Вложение', square: true });
    let customUrlStored = customUrl(tpl);

    const photoGrid = h('div', { class: 'messages-photo-grid' },
      h('label', { class: 'messages-photo-opt' }, staffPhoto, h('span', { class: 'messages-photo-icon' }, icon('users')), h('span', null, 'Фото мастера')),
      h('label', { class: 'messages-photo-opt' }, coverPhoto, h('span', { class: 'messages-photo-icon' }, icon('globe')), h('span', null, 'Обложка профиля')),
      h('div', { class: 'messages-photo-opt messages-photo-custom' }, custom.el),
    );

    const previewBtn = h('button', { class: 'btn sm soft', type: 'button' }, icon('chat'), 'Обновить превью');
    previewBtn.addEventListener('click', () => runPreview());

    const save = h('button', { class: 'btn primary', type: 'button' }, icon('check'), 'Сохранить');
    save.addEventListener('click', () =>
      withBusy(save, async () => {
        try {
          const slots = [];
          if (staffPhoto.checked) slots.push('staff');
          if (coverPhoto.checked) slots.push('venue_cover');
          const file = custom.getFile();
          if (file) {
            const up = await api.upload('/manager/messages/photo', file);
            slots.push({ type: 'custom', url: up.url });
            customUrlStored = up.url;
          } else if (customUrlStored) {
            slots.push({ type: 'custom', url: customUrlStored });
          }
          await api.put(`/manager/messages/${activeKind}`, {
            body: editor.getBody(),
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

    const layout = h('div', { class: 'messages-layout' },
      h('div', { class: 'card pad messages-editor' },
        h('p', { class: 'messages-kind-hint' }, KIND_HINTS[activeKind] || ''),
        field(
          'Текст напоминания',
          editor.el,
          'Поддерживается HTML: <b>, <i>, ссылки. Переменные вставляйте кнопками ниже.',
        ),
        h('div', { class: 'messages-block' },
          h('span', { class: 'label' }, 'Переменные'),
          tokenChips,
        ),
        h('div', { class: 'messages-block' },
          h('span', { class: 'label' }, 'Вложения к напоминанию'),
          photoGrid,
        ),
        h('div', { class: 'messages-actions row' }, previewBtn, save),
      ),
      h('div', { class: 'messages-aside' },
        h('div', { class: 'label', style: { marginBottom: '8px' } }, 'Как увидит клиент'),
        h('div', { class: 'msg-tg-shell card' },
          h('div', { class: 'msg-tg-bar' }, h('span', null, 'Telegram'), h('span', { class: 'chip ok' }, 'бот')),
          h('div', { class: 'msg-tg-chat' }, previewEl),
        ),
        h(
          'p',
          { class: 'tiny muted messages-preview-note' },
          tgWebApp
            ? 'В Telegram превью обновляется по кнопке «Обновить превью». Пример с тестовыми данными.'
            : 'Пример с тестовыми данными. Реальный текст зависит от записи.',
        ),
      ),
    );

    panel.replaceChildren(layout);
    schedulePreview();
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
    panel.replaceChildren(h('div', { class: 'empty card' }, h('h3', null, 'Не удалось загрузить'), h('p', null, friendly(e))));
  }
  return root;
}