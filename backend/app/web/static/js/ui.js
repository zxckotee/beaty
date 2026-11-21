import { h, icon, hueFor, initials, clear } from './util.js';

const overlayRoot = () => document.getElementById('overlay-root');
const stack = [];

export function avatar(person, size = '', { eager = false } = {}) {
  const name = person.name || person.display_name || '?';
  const el = h('div', { class: `avatar ${size}`, style: { '--h': hueFor(name) }, title: name });
  if (person.photo_url) {
    const imgAttrs = { src: person.photo_url, alt: name };
    if (!eager) imgAttrs.loading = 'lazy';
    const img = h('img', imgAttrs);
    img.addEventListener('error', () => {
      img.remove();
      el.append(initials(name));
    });
    el.append(img);
  } else {
    el.append(initials(name));
  }
  return el;
}

export function toast(message, isError = false) {
  const root = document.getElementById('toast-root');
  const el = h('div', { class: `toast ${isError ? 'err' : ''}` }, message);
  root.append(el);
  setTimeout(() => el.remove(), isError ? 5200 : 3200);
}

function onKey(e) {
  if (e.key === 'Escape' && stack.length) stack[stack.length - 1].close();
}
document.addEventListener('keydown', onKey);

/** Opens a bottom sheet (mobile) / modal (desktop). Returns { close, body, setFooter }. */
export function openSheet({ title, build, onClose }) {
  const body = h('div', { class: 'sheet-body' });
  const foot = h('div', { class: 'sheet-foot' });
  const closeBtn = h('button', { class: 'btn ghost icon-btn', type: 'button', 'aria-label': 'Закрыть' }, icon('close'));
  const sheet = h(
    'div',
    { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    h('div', { class: 'grab' }),
    h('div', { class: 'sheet-head' }, h('h2', null, title), closeBtn),
    body,
    foot,
  );
  const overlay = h('div', { class: 'overlay' }, sheet);
  const handle = {
    body,
    foot,
    close() {
      const i = stack.indexOf(handle);
      if (i >= 0) stack.splice(i, 1);
      overlay.remove();
      if (!stack.length) document.body.style.overflow = '';
      if (onClose) onClose();
    },
    setFooter(...nodes) {
      clear(foot);
      foot.append(...nodes);
    },
  };
  closeBtn.addEventListener('click', handle.close);
  overlay.addEventListener('mousedown', (e) => {
    if (e.target === overlay) handle.close();
  });
  stack.push(handle);
  overlayRoot().append(overlay);
  document.body.style.overflow = 'hidden';
  build(handle);
  const focusable = sheet.querySelector('input, select, textarea');
  if (focusable && matchMedia('(hover: hover)').matches) focusable.focus();
  return handle;
}

export function confirmDialog({ title, text, confirmLabel = 'Подтвердить', danger = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (v) => {
      if (settled) return;
      settled = true;
      resolve(v);
    };
    openSheet({
      title,
      onClose: () => finish(false),
      build: (s) => {
        s.body.append(h('p', { class: 'muted' }, text));
        s.setFooter(
          h('button', { class: 'btn', type: 'button', onclick: () => s.close() }, 'Отмена'),
          h(
            'button',
            {
              class: `btn ${danger ? 'danger' : 'primary'}`,
              type: 'button',
              onclick: () => {
                finish(true);
                s.close();
              },
            },
            confirmLabel,
          ),
        );
      },
    });
  });
}

export function spinner() {
  return h('div', { class: 'spinner', role: 'progressbar', 'aria-label': 'Загрузка' });
}

export function emptyState(emoji, title, text, action) {
  return h('div', { class: 'empty card' }, h('div', { class: 'big' }, emoji), h('h3', null, title), h('p', null, text), action);
}

export function field(label, control, hint) {
  return h('div', { class: 'field' }, h('label', null, label), control, hint ? h('span', { class: 'tiny muted' }, hint) : null);
}

export async function withBusy(button, fn) {
  button.disabled = true;
  try {
    return await fn();
  } finally {
    button.disabled = false;
  }
}

/** Avatar-like preview with a "choose photo" button. getFile() returns the picked File or null. */
export function photoPicker({ url, name, square = false }) {
  let file = null;
  let objectUrl = null;
  const preview = h('div');
  const draw = (src, label) => {
    preview.replaceChildren(avatar({ name: label || name || '?', photo_url: src }, `lg ${square ? 'sq' : ''}`, { eager: true }));
  };
  draw(url, name);
  const input = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/gif', class: 'sr', tabindex: '-1' });
  input.addEventListener('change', () => {
    const picked = input.files && input.files[0] ? input.files[0] : null;
    file = picked;
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    if (picked) {
      objectUrl = URL.createObjectURL(picked);
      draw(objectUrl, name);
    } else {
      draw(url, name);
    }
  });
  const pick = () => {
    input.value = '';
    input.click();
  };
  const btn = h('button', { class: 'btn sm', type: 'button', onclick: pick }, icon('camera'), 'Выбрать фото');
  const el = h('div', { class: 'photo-field' }, preview, h('div', { class: 'col', style: { gap: '6px' } }, btn, h('span', { class: 'tiny muted' }, 'JPG, PNG, WebP до 5 МБ'), input));
  return {
    el,
    getFile: () => file,
    setServerUrl(src) {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = null;
      }
      file = null;
      draw(src, name);
    },
    setName(next) {
      name = next;
    },
  };
}
