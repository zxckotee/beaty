import { h, icon, socialBrandIcon } from './util.js';

export const WIDGET_TEMPLATES = {
  story: { label: 'Текст', hint: 'Заголовок и абзацы' },
  visual: { label: 'Фото + текст', hint: 'Крупное фото с подписью' },
  gallery: { label: 'Галерея', hint: 'До 5 фото' },
  split: { label: 'Колонка', hint: 'Фото и текст рядом' },
  highlight: { label: 'Акцент', hint: 'Цветная плашка' },
  social_row: { label: 'Соцсети', hint: 'Кнопки ВК, Telegram, MAX' },
  cta_card: { label: 'Запись', hint: 'Текст и кнопка записи' },
};

const PRESET_LABELS = {
  vk: 'Мы ВКонтакте',
  telegram: 'Мы в Telegram',
  max: 'Мы в MAX',
};

const PRESET_CLASS = {
  vk: 'pw-action--vk',
  telegram: 'pw-action--telegram',
  max: 'pw-action--max',
};

const SIZE_CLASS = { sm: 'pw-size-sm', md: 'pw-size-md', lg: 'pw-size-lg', xl: 'pw-size-xl' };
const FONT_CLASS = { sans: 'pw-font-sans', serif: 'pw-font-serif', display: 'pw-font-display' };

function blockStyleEl(style = {}) {
  const out = {};
  if (style.color) out.color = style.color;
  if (style.bg) {
    out.backgroundColor = style.bg;
    out.padding = '6px 10px';
    out.borderRadius = '10px';
    out.display = 'inline-block';
  }
  return out;
}

function renderBlock(block) {
  if (!block || !block.content) return null;
  const tag = block.kind === 'heading' ? 'h3' : 'p';
  const cls = [
    'pw-block',
    block.kind === 'heading' ? 'pw-heading' : 'pw-text',
    FONT_CLASS[styleKey(block, 'font')],
    SIZE_CLASS[styleKey(block, 'size')],
  ]
    .filter(Boolean)
    .join(' ');
  const style = blockStyleEl(block.style);
  return h(tag, { class: cls, style }, block.content);
}

function styleKey(block, key) {
  return (block.style && block.style[key]) || (block.kind === 'heading' ? (key === 'size' ? 'lg' : 'display') : key === 'size' ? 'md' : 'sans');
}

function actionStyleInline(st = {}, preset) {
  const s = {};
  if (st.color) s['--pw-btn-bg'] = st.color;
  if (st.textColor) s['--pw-btn-fg'] = st.textColor;
  return s;
}

function renderAction(action, ctx) {
  if (!action) return null;
  const preset = action.preset;
  const label =
    (action.label && action.label.trim()) ||
    (preset && PRESET_LABELS[preset]) ||
    (action.kind === 'book' ? 'Записаться' : 'Перейти');
  const variant = (action.style && action.style.variant) || 'filled';
  const classes = [
    'pw-action',
    `pw-action--${variant}`,
    preset && PRESET_CLASS[preset] ? PRESET_CLASS[preset] : '',
  ]
    .filter(Boolean)
    .join(' ');
  const style = actionStyleInline(action.style || {}, preset);
  const kids = [];
  if (action.icon && action.icon !== 'none' && action.kind === 'book') kids.push(icon(action.icon));
  if (preset) kids.push(socialBrandIcon(preset));
  kids.push(label);

  if (action.kind === 'book') {
    if (ctx.mode === 'studio') {
      return h('a', { class: classes, style, href: ctx.bookHref || '#book' }, ...kids);
    }
    const btn = h('button', { class: classes, style, type: 'button' }, ...kids);
    if (ctx.onBook) btn.addEventListener('click', (e) => { e.preventDefault(); ctx.onBook(); });
    return btn;
  }
  const href = action.href || '#';
  return h('a', { class: classes, style, href, target: '_blank', rel: 'noopener noreferrer' }, ...kids);
}

function renderPhotos(photos, template) {
  const urls = (photos || []).filter(Boolean);
  if (!urls.length) return null;
  if (template === 'visual' || (template === 'split' && urls.length === 1)) {
    return h('div', { class: 'pw-visual-photo' }, h('img', { src: urls[0], alt: '', loading: 'lazy' }));
  }
  const grid = h('div', { class: `pw-gallery pw-gallery--${Math.min(urls.length, 5)}` });
  for (const url of urls.slice(0, 5)) grid.append(h('img', { src: url, alt: '', loading: 'lazy' }));
  return grid;
}

export function renderProfileWidget(widget, ctx = { mode: 'app' }) {
  const template = widget.template || 'story';
  const payload = widget.payload || {};
  const blocks = (payload.blocks || []).map(renderBlock).filter(Boolean);
  const photos = renderPhotos(payload.photos, template);
  const actions = (payload.actions || []).map((a) => renderAction(a, ctx)).filter(Boolean);
  const inner = h('div', { class: `pw-inner pw-tpl-${template}` });

  if (template === 'split' && photos) {
    inner.append(h('div', { class: 'pw-split' }, photos, h('div', { class: 'pw-split-text' }, ...blocks)));
  } else if (template === 'highlight') {
    inner.classList.add('pw-highlight-card');
    inner.append(...blocks, photos, actions.length ? h('div', { class: 'pw-actions' }, ...actions) : null);
  } else if (template === 'social_row') {
    if (blocks.length) inner.append(...blocks);
    if (actions.length) inner.append(h('div', { class: 'pw-actions pw-actions--row' }, ...actions));
  } else if (template === 'cta_card') {
    inner.append(...blocks, actions.length ? h('div', { class: 'pw-actions pw-actions--center' }, ...actions) : null);
  } else if (template === 'visual') {
    inner.append(photos, h('div', { class: 'pw-visual-copy' }, ...blocks, actions.length ? h('div', { class: 'pw-actions' }, ...actions) : null));
  } else if (template === 'gallery') {
    inner.append(photos, ...blocks, actions.length ? h('div', { class: 'pw-actions' }, ...actions) : null);
  } else {
    inner.append(...blocks, photos, actions.length ? h('div', { class: 'pw-actions' }, ...actions) : null);
  }

  const root = h('article', {
    class: `pw${ctx.previewWide ? ' pw--wide' : ''}${ctx.previewPhone ? ' pw--phone' : ''}${widget.is_visible === false ? ' pw--hidden' : ''}`,
    'data-widget-id': widget.id || '',
  }, inner);
  return root;
}

export function defaultPayloadForTemplate(template) {
  const base = { blocks: [], photos: [], actions: [] };
  switch (template) {
    case 'story':
      base.blocks = [
        { kind: 'heading', content: 'О нас', style: { font: 'display', size: 'lg', color: null, bg: null } },
        { kind: 'text', content: 'Расскажите клиентам, чем вы отличаетесь.', style: { font: 'sans', size: 'md', color: null, bg: null } },
      ];
      break;
    case 'visual':
      base.blocks = [
        { kind: 'heading', content: 'Наш стиль', style: { font: 'display', size: 'lg', color: null, bg: null } },
        { kind: 'text', content: 'Кратко опишите услугу или атмосферу.', style: { font: 'sans', size: 'md', color: null, bg: null } },
      ];
      break;
    case 'gallery':
      base.blocks = [
        { kind: 'text', content: 'Подборка работ или интерьера.', style: { font: 'sans', size: 'md', color: null, bg: null } },
      ];
      break;
    case 'split':
      base.blocks = [
        { kind: 'heading', content: 'Почему мы', style: { font: 'display', size: 'lg', color: null, bg: null } },
        { kind: 'text', content: 'Два-три преимущества в свободной форме.', style: { font: 'sans', size: 'md', color: null, bg: null } },
      ];
      break;
    case 'highlight':
      base.blocks = [
        { kind: 'heading', content: 'Акция', style: { font: 'display', size: 'xl', color: null, bg: null } },
        { kind: 'text', content: 'Условия и сроки — коротко и ясно.', style: { font: 'sans', size: 'md', color: null, bg: null } },
      ];
      break;
    case 'social_row':
      base.blocks = [
        { kind: 'heading', content: 'Мы на связи', style: { font: 'display', size: 'md', color: null, bg: null } },
      ];
      base.actions = [
        { kind: 'link', label: PRESET_LABELS.vk, href: 'https://vk.com/', preset: 'vk', icon: 'none', style: { variant: 'filled', color: null, textColor: null } },
        { kind: 'link', label: PRESET_LABELS.telegram, href: 'https://t.me/', preset: 'telegram', icon: 'none', style: { variant: 'filled', color: null, textColor: null } },
        { kind: 'link', label: PRESET_LABELS.max, href: 'https://max.ru/', preset: 'max', icon: 'none', style: { variant: 'filled', color: null, textColor: null } },
      ];
      break;
    case 'cta_card':
      base.blocks = [
        { kind: 'heading', content: 'Запишитесь онлайн', style: { font: 'display', size: 'lg', color: null, bg: null } },
        { kind: 'text', content: 'Выберите услугу и удобное время в пару касаний.', style: { font: 'sans', size: 'md', color: null, bg: null } },
      ];
      base.actions = [
        { kind: 'book', label: 'Записаться', href: null, preset: null, icon: 'calendar', style: { variant: 'filled', color: null, textColor: null } },
      ];
      break;
    default:
      break;
  }
  return base;
}