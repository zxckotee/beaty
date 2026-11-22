const TOKEN_RE = /\{([a-z_]+)\}/g;

/**
 * @param {Record<string, string>} tokenMap - e.g. { service: "Услуга", ... }
 */
export function createTokenEditor({ body = '', tokens = [], onInput } = {}) {
  const tokenMap = Object.fromEntries(tokens);

  const el = document.createElement('div');
  el.className = 'textarea messages-text msg-token-editable';
  el.contentEditable = 'true';
  el.setAttribute('role', 'textbox');
  el.setAttribute('aria-multiline', 'true');
  el.spellcheck = false;

  function setBody(raw) {
    el.replaceChildren(...bodyToFragment(String(raw || ''), tokenMap));
  }

  function getBody() {
    return fragmentToBody(el);
  }

  function insertToken(key) {
    const label = tokenMap[key] || key;
    const span = document.createElement('span');
    span.className = 'msg-token';
    span.contentEditable = 'false';
    span.dataset.token = key;
    span.textContent = label;

    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) {
      el.appendChild(span);
      el.appendChild(document.createTextNode('\u00a0'));
    } else {
      const range = sel.getRangeAt(0);
      if (!el.contains(range.commonAncestorContainer)) {
        el.appendChild(span);
      } else {
        range.deleteContents();
        range.insertNode(span);
        range.setStartAfter(span);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
      }
    }
    el.focus();
    onInput?.();
  }

  el.addEventListener('input', () => onInput?.());

  setBody(body);

  return { el, setBody, getBody, insertToken, focus: () => el.focus() };
}

function bodyToFragment(body, tokenMap) {
  const nodes = [];
  let last = 0;
  let match;
  TOKEN_RE.lastIndex = 0;
  while ((match = TOKEN_RE.exec(body)) !== null) {
    if (match.index > last) {
      appendHtmlChunk(nodes, body.slice(last, match.index));
    }
    const key = match[1];
    const span = document.createElement('span');
    span.className = 'msg-token';
    span.contentEditable = 'false';
    span.dataset.token = key;
    span.textContent = tokenMap[key] || key;
    nodes.push(span);
    last = match.index + match[0].length;
  }
  if (last < body.length) {
    appendHtmlChunk(nodes, body.slice(last));
  }
  return nodes;
}

function appendHtmlChunk(nodes, html) {
  if (!html) return;
  const wrap = document.createElement('div');
  wrap.innerHTML = html;
  while (wrap.firstChild) {
    nodes.push(wrap.firstChild);
  }
}

function fragmentToBody(container) {
  let out = '';
  for (const child of container.childNodes) {
    out += serializeNode(child);
  }
  return out;
}

function serializeNode(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent || '';
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return '';
  }
  const el = /** @type {HTMLElement} */ (node);
  if (el.classList.contains('msg-token')) {
    return `{${el.dataset.token || ''}}`;
  }
  const tag = el.tagName.toLowerCase();
  if (tag === 'br') {
    return '\n';
  }
  const inner = fragmentToBody(el);
  if (tag === 'b' || tag === 'strong') {
    return `<b>${inner}</b>`;
  }
  if (tag === 'i' || tag === 'em') {
    return `<i>${inner}</i>`;
  }
  if (tag === 'a') {
    const href = el.getAttribute('href') || '';
    return `<a href="${escapeAttr(href)}">${inner}</a>`;
  }
  if (tag === 'div' || tag === 'p') {
    return `${inner}\n`;
  }
  return inner;
}

function escapeAttr(value) {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}