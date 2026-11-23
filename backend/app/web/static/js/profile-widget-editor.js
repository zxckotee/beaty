import { api, friendly } from './api.js';
import { navigate } from './main.js';
import { field, openSheet, photoPicker, toast, withBusy } from './ui.js';
import { h, icon } from './util.js';
import { WIDGET_TEMPLATES, defaultPayloadForTemplate, renderProfileWidget } from './profile-widgets.js?v=17';

function clonePayload(p) {
  return JSON.parse(JSON.stringify(p || { blocks: [], photos: [], actions: [] }));
}

function styleFields(style, onChange) {
  const row = h('div', { class: 'wb-style-grid' });
  const font = h('select', { class: 'inp' });
  for (const v of ['sans', 'serif', 'display']) {
    const o = h('option', { value: v }, v === 'sans' ? 'Обычный' : v === 'serif' ? 'Классика' : 'Заголовок');
    if ((style.font || 'sans') === v) o.selected = true;
    font.append(o);
  }
  font.addEventListener('change', () => onChange({ ...style, font: font.value }));

  const size = h('select', { class: 'inp' });
  for (const [v, label] of [
    ['sm', 'Мелкий'],
    ['md', 'Средний'],
    ['lg', 'Крупный'],
    ['xl', 'Очень крупный'],
  ]) {
    const o = h('option', { value: v }, label);
    if ((style.size || 'md') === v) o.selected = true;
    size.append(o);
  }
  size.addEventListener('change', () => onChange({ ...style, size: size.value }));

  const color = h('input', { class: 'inp', type: 'text', placeholder: '#RRGGBB', value: style.color || '' });
  color.addEventListener('change', () => onChange({ ...style, color: color.value.trim() || null }));

  const bg = h('input', { class: 'inp', type: 'text', placeholder: 'Фон #RRGGBB', value: style.bg || '' });
  bg.addEventListener('change', () => onChange({ ...style, bg: bg.value.trim() || null }));

  const presets = h('div', { class: 'wb-presets row' });
  for (const [label, next] of [
    ['Акцент', { color: 'var(--accent)', bg: style.bg }],
    ['Нейтраль', { color: 'var(--muted)', bg: style.bg }],
    ['Светлый фон', { color: style.color, bg: 'color-mix(in srgb, var(--accent) 14%, var(--surface))' }],
  ]) {
    presets.append(
      h('button', {
        class: 'btn sm ghost',
        type: 'button',
        onclick: () => onChange({ ...style, ...next }),
      }, label),
    );
  }

  row.append(
    field('Шрифт', font),
    field('Размер', size),
    field('Цвет текста', color),
    field('Фон фрагмента', bg),
    h('p', { class: 'tiny muted' }, 'Быстрые пресеты'),
    presets,
  );
  return row;
}

function actionStyleFields(action, index, state, refreshPreview) {
  const st = action.style || { variant: 'filled', color: null, textColor: null };
  const variant = h('select', { class: 'inp' });
  for (const v of ['filled', 'outline', 'ghost']) {
    const o = h('option', { value: v }, v);
    if (st.variant === v) o.selected = true;
    variant.append(o);
  }
  const iconSel = h('select', { class: 'inp' });
  for (const [v, label] of [
    ['none', 'Без иконки'],
    ['calendar', 'Календарь'],
    ['scissors', 'Ножницы'],
    ['phone', 'Телефон'],
  ]) {
    const o = h('option', { value: v }, label);
    if ((action.icon || 'none') === v) o.selected = true;
    iconSel.append(o);
  }
  const labelInp = h('input', { class: 'inp', value: action.label || '' });
  const hrefInp = action.kind === 'link' ? h('input', { class: 'inp', value: action.href || '', placeholder: 'https://…' }) : null;

  const apply = () => {
    state.payload.actions[index] = {
      ...state.payload.actions[index],
      label: labelInp.value.trim(),
      href: hrefInp ? hrefInp.value.trim() : null,
      icon: iconSel.value,
      style: {
        ...st,
        variant: variant.value,
        color: colorInp.value.trim() || null,
        textColor: fgInp.value.trim() || null,
      },
    };
    refreshPreview();
  };
  const colorInp = h('input', { class: 'inp', placeholder: 'Фон кнопки', value: st.color || '' });
  const fgInp = h('input', { class: 'inp', placeholder: 'Текст кнопки', value: st.textColor || '' });
  variant.addEventListener('change', apply);
  iconSel.addEventListener('change', apply);
  labelInp.addEventListener('change', apply);
  if (hrefInp) hrefInp.addEventListener('change', apply);
  colorInp.addEventListener('change', apply);
  fgInp.addEventListener('change', apply);

  const wrap = h('div', { class: 'card wb-action-card' }, h('h4', null, action.kind === 'book' ? 'Кнопка записи' : 'Ссылка'));
  wrap.append(
    field('Подпись', labelInp),
    action.kind === 'link' ? field('URL', hrefInp) : null,
    field('Иконка', iconSel),
    field('Стиль', variant),
    field('Цвет кнопки', colorInp),
    field('Цвет текста', fgInp),
  );
  return wrap;
}

function buildEditor(state, sheet, { onSaved }) {
  let previewWide = false;
  const previewHost = h('div', { class: 'wb-preview-frame' });
  const inspector = h('div', { class: 'wb-inspector' });

  function refreshPreview() {
    previewHost.replaceChildren();
    const node = renderProfileWidget(
      { id: state.id, template: state.template, payload: state.payload, is_visible: true },
      { mode: 'app', onBook: () => navigate('book'), previewWide, previewPhone: !previewWide },
    );
    previewHost.append(node);
  }

  function redrawInspector() {
    inspector.replaceChildren();
    const blocksSec = h('section', null, h('h3', { class: 'wb-h' }, 'Текст'));
    state.payload.blocks.forEach((block, i) => {
      const ta = h('textarea', { class: 'inp', rows: block.kind === 'heading' ? 2 : 4 }, block.content || '');
      ta.addEventListener('input', () => {
        state.payload.blocks[i].content = ta.value;
        refreshPreview();
      });
      const sty = styleFields(block.style || {}, (next) => {
        state.payload.blocks[i].style = next;
        refreshPreview();
      });
      blocksSec.append(
        h('div', { class: 'wb-block-edit card' },
          h('span', { class: 'tiny muted' }, block.kind === 'heading' ? 'Заголовок' : 'Текст'),
          ta,
          sty,
        ),
      );
    });

    const addBlockRow = h('div', { class: 'row' });
    addBlockRow.append(
      h('button', {
        class: 'btn sm ghost',
        type: 'button',
        onclick: () => {
          state.payload.blocks.push({ kind: 'text', content: '', style: { font: 'sans', size: 'md', color: null, bg: null } });
          redrawInspector();
          refreshPreview();
        },
      }, '+ Абзац'),
    );

    const photosSec = h('section', null, h('h3', { class: 'wb-h' }, 'Фото (до 5)'));
    const photoGrid = h('div', { class: 'wb-photo-grid' });
    const urls = state.payload.photos || [];
    urls.forEach((url, idx) => {
      photoGrid.append(
        h('div', { class: 'wb-photo-slot' },
          h('img', { src: url, alt: '' }),
          h('button', {
            class: 'btn sm danger',
            type: 'button',
            onclick: () => {
              state.payload.photos.splice(idx, 1);
              redrawInspector();
              refreshPreview();
            },
          }, '×'),
        ),
      );
    });
  if (urls.length < 5) {
    const pick = photoPicker({ url: null, name: 'фото' });
    pick.el.querySelector('input')?.addEventListener('change', async () => {
      const f = pick.getFile();
      if (!f) return;
      try {
        let wId = state.id;
        if (!wId) {
          const created = await api.post('/manager/landing/widgets', {
            template: state.template,
            payload: state.payload,
            sort_order: state.sort_order ?? 0,
          });
          state.id = created.id;
          wId = created.id;
        }
        const r = await api.upload(`/manager/landing/widgets/${wId}/photos`, f);
        state.payload.photos = r.photos || [];
        redrawInspector();
        refreshPreview();
      } catch (e) {
        toast(friendly(e), true);
      }
    });
    photoGrid.append(pick.el);
  }
    photosSec.append(photoGrid);

    const actionsSec = h('section', null, h('h3', { class: 'wb-h' }, 'Кнопки'));
    (state.payload.actions || []).forEach((action, i) => actionsSec.append(actionStyleFields(action, i, state, refreshPreview)));
    const actionBtns = h('div', { class: 'row' });
    if (!state.payload.actions.some((a) => a.kind === 'book')) {
      actionBtns.append(
        h('button', {
          class: 'btn sm',
          type: 'button',
          onclick: () => {
            state.payload.actions.push({
              kind: 'book',
              label: 'Записаться',
              icon: 'calendar',
              style: { variant: 'filled', color: null, textColor: null },
            });
            redrawInspector();
            refreshPreview();
          },
        }, '+ Запись'),
      );
    }
    actionBtns.append(
      h('button', {
        class: 'btn sm ghost',
        type: 'button',
        onclick: () => {
          state.payload.actions.push({
            kind: 'link',
            label: 'Ссылка',
            href: 'https://',
            preset: 'custom',
            icon: 'none',
            style: { variant: 'outline', color: null, textColor: null },
          });
          redrawInspector();
          refreshPreview();
        },
      }, '+ Ссылка'),
    );
    actionsSec.append(actionBtns);

    inspector.append(blocksSec, addBlockRow, photosSec, actionsSec);
  }

  const toggle = h('div', { class: 'wb-toggle row' },
    h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { previewWide = false; refreshPreview(); } }, 'Телефон'),
    h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { previewWide = true; refreshPreview(); } }, 'Широкий'),
  );

  redrawInspector();
  refreshPreview();

  sheet.body.replaceChildren(
    h('div', { class: 'widget-builder-layout' },
      h('div', { class: 'wb-preview-col' }, toggle, previewHost),
      inspector,
    ),
  );

  sheet.setFooter(
    h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'),
    h('button', {
      class: 'btn primary',
      type: 'button',
      onclick: (ev) => withBusy(ev.currentTarget, async () => {
        try {
          const body = { template: state.template, payload: state.payload };
          if (state.id) await api.patch(`/manager/landing/widgets/${state.id}`, body);
          else {
            const created = await api.post('/manager/landing/widgets', {
              ...body,
              sort_order: state.sort_order ?? 0,
            });
            state.id = created.id;
          }
          toast('Виджет сохранён');
          if (onSaved) await onSaved();
          sheet.close();
        } catch (e) {
          toast(friendly(e), true);
        }
      }),
    }, 'Сохранить'),
  );
}

function thumbLine(wide, short) {
  const cls = ['wb-thumb-line', wide ? 'wb-thumb-line--lg' : '', short ? 'wb-thumb-line--short' : ''].filter(Boolean).join(' ');
  return h('span', { class: cls, 'aria-hidden': 'true' });
}

function templatePreviewThumb(templateId) {
  const root = h('div', { class: `wb-thumb wb-thumb--${templateId}`, 'aria-hidden': 'true' });
  switch (templateId) {
    case 'story':
      root.append(thumbLine(true), thumbLine(false), thumbLine(false, true));
      break;
    case 'visual':
      root.append(
        h('span', { class: 'wb-thumb-photo wb-thumb-photo--hero' }),
        thumbLine(true),
        thumbLine(false, true),
      );
      break;
    case 'gallery':
      root.append(
        h('span', { class: 'wb-thumb-gallery' },
          h('span'), h('span'), h('span'), h('span'),
        ),
        thumbLine(false, true),
      );
      break;
    case 'split':
      root.append(
        h('span', { class: 'wb-thumb-split' },
          h('span', { class: 'wb-thumb-photo' }),
          h('span', { class: 'wb-thumb-split-text' }, thumbLine(true), thumbLine(false, true)),
        ),
      );
      break;
    case 'highlight':
      root.append(
        h('span', { class: 'wb-thumb-highlight' }, thumbLine(true), thumbLine(false), thumbLine(false, true)),
      );
      break;
    case 'social_row':
      root.append(
        thumbLine(true, true),
        h('span', { class: 'wb-thumb-pills' }, h('span'), h('span'), h('span')),
      );
      break;
    case 'cta_card':
      root.append(thumbLine(true), thumbLine(false, true), h('span', { class: 'wb-thumb-cta' }));
      break;
    default:
      root.append(thumbLine(true), thumbLine(false));
  }
  return root;
}

function pickTemplate(onPick) {
  const grid = h('div', { class: 'wb-template-grid' });
  for (const [id, meta] of Object.entries(WIDGET_TEMPLATES)) {
    grid.append(
      h('button', {
        class: 'wb-template-card card',
        type: 'button',
        onclick: () => onPick(id),
      },
        templatePreviewThumb(id),
        h('span', { class: 'wb-template-meta' },
          h('strong', null, meta.label),
          h('span', { class: 'tiny muted' }, meta.hint),
        ),
      ),
    );
  }
  return grid;
}

export function openWidgetEditor(widget, { sortOrder = 0, onSaved } = {}) {
  if (!widget) {
    openSheet({
      title: 'Новый виджет',
      size: 'builder',
      build: (sheet) => {
        sheet.body.append(
          h('p', { class: 'muted' }, 'Выберите шаблон — он уже адаптирован под телефон и десктоп.'),
          pickTemplate((template) => {
            const state = {
              id: null,
              template,
              payload: defaultPayloadForTemplate(template),
              sort_order: sortOrder,
            };
            sheet.body.replaceChildren();
            buildEditor(state, sheet, { onSaved });
          }),
        );
      },
    });
    return;
  }
  openSheet({
    title: 'Редактор виджета',
    size: 'builder',
    build: (sheet) => {
      const state = {
        id: widget.id,
        template: widget.template,
        payload: clonePayload(widget.payload),
        sort_order: widget.sort_order,
      };
      buildEditor(state, sheet, { onSaved });
    },
  });
}