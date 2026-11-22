import { api, friendly, tenantId } from '../api.js';
import { debounce, h, icon } from '../util.js';
import { spinner, toast, withBusy } from '../ui.js';

const POLL_MS = 4000;

async function postChatForm(path, formData) {
  const res = await fetch(`/api/t/${encodeURIComponent(tenantId)}/manager/chat${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    body: formData,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data && typeof data.detail === 'string' ? data.detail : res.statusText;
    throw new Error(detail);
  }
  return data;
}

function mediaUrl(messageId) {
  return `/media/chat/${encodeURIComponent(tenantId)}/${messageId}`;
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function renderBubble(msg) {
  const mine = msg.direction === 'outbound';
  const inner = [];
  if (msg.kind === 'photo' && msg.has_media) {
    inner.push(h('img', { class: 'chat-img', src: mediaUrl(msg.id), alt: '', loading: 'lazy' }));
    if (msg.body) inner.push(h('p', { class: 'chat-text' }, msg.body));
  } else if (msg.kind === 'voice' && msg.has_media) {
    inner.push(h('audio', { class: 'chat-audio', controls: true, preload: 'metadata', src: mediaUrl(msg.id) }));
  } else if (msg.body) {
    inner.push(h('p', { class: 'chat-text' }, msg.body));
  }
  const author =
    msg.author === 'manager' ? 'Вы (бот)' : msg.author === 'client' ? 'Клиент' : 'Бот';
  return h(
    'div',
    { class: `chat-bubble ${mine ? 'out' : 'in'}` },
    h('div', { class: 'chat-meta muted small' }, `${author} · ${formatTime(msg.created_at)}`),
    ...inner,
  );
}

export async function chatsView(clientId = '') {
  const root = h('div', { class: 'chats-page' });

  if (clientId) {
    return threadView(root, clientId);
  }
  return listView(root);
}

async function listView(root) {
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Имя или телефон', autocomplete: 'off' });
  const list = h('div', { class: 'chat-list' });
  root.append(
    h('div', { class: 'page-head' }, h('div', null, h('h1', null, 'Чаты'), h('p', { class: 'muted' }, 'Переписка клиентов с ботом в Telegram'))),
    search,
    list,
  );
  list.append(spinner());

  const load = debounce(async () => {
    try {
      const q = search.value.trim();
      const res = await api.get(`/manager/chat/clients?q=${encodeURIComponent(q)}`);
      draw(res.items || []);
    } catch (e) {
      toast(friendly(e), true);
    }
  }, 300);

  function draw(items) {
    if (!items.length) {
      list.replaceChildren(h('p', { class: 'muted' }, 'Нет клиентов с Telegram или ничего не найдено.'));
      return;
    }
    list.replaceChildren(
      ...items.map((c) =>
        h(
          'button',
          {
            type: 'button',
            class: 'chat-list-item',
            onclick: () => {
              location.hash = `#/chats/${c.id}`;
            },
          },
          h('div', { class: 'chat-list-main' }, h('strong', null, c.name), c.phone ? h('span', { class: 'muted small' }, c.phone) : null),
          h('p', { class: 'chat-list-preview muted small' }, c.last_preview || 'Нет сообщений'),
          c.telegram_unreachable
            ? h('span', { class: 'chip warn' }, 'Telegram недоступен')
            : null,
        ),
      ),
    );
  }

  search.addEventListener('input', load);
  await load();
  return root;
}

async function threadView(root, clientId) {
  const feed = h('div', { class: 'chat-feed', role: 'log' });
  const composer = h('div', { class: 'chat-composer' });
  const text = h('textarea', { class: 'textarea chat-input', rows: 2, placeholder: 'Сообщение от имени бота…' });
  const photoInput = h('input', { type: 'file', accept: 'image/*', hidden: true });
  const voiceInput = h('input', { type: 'file', accept: 'audio/*,.ogg', hidden: true });
  let pollTimer = null;
  let clientMeta = null;

  root.append(
    h(
      'div',
      { class: 'page-head' },
      h('a', { class: 'btn ghost sm', href: '#/chats' }, icon('chevL'), 'Назад'),
      h('div', { id: 'chat-head-title' }, spinner()),
    ),
    feed,
    composer,
  );

  composer.append(
    text,
    h(
      'div',
      { class: 'chat-composer-bar' },
      h('button', { class: 'btn ghost icon-btn', type: 'button', title: 'Фото', onclick: () => photoInput.click() }, icon('camera')),
      h('button', { class: 'btn ghost icon-btn', type: 'button', title: 'Голос из файла', onclick: () => voiceInput.click() }, icon('phone')),
      h('button', { class: 'btn ghost icon-btn', type: 'button', title: 'Записать', id: 'chat-rec-btn' }, icon('phone')),
      h('button', { class: 'btn primary', type: 'button', onclick: sendText }, 'Отправить')),
    photoInput,
    voiceInput,
  );

  let recorder = null;
  let recordChunks = [];

  async function sendText() {
    const body = text.value.trim();
    if (!body) return;
    const fd = new FormData();
    fd.append('text', body);
    try {
      await withBusy(composer, () => postChatForm(`/clients/${clientId}/messages`, fd));
      text.value = '';
      await refresh(false);
    } catch (e) {
      toast(e.message || friendly(e), true);
    }
  }

  async function sendFile(file, field) {
    const fd = new FormData();
    fd.append(field, file);
    const cap = text.value.trim();
    if (cap) fd.append('text', cap);
    try {
      await withBusy(composer, () => postChatForm(`/clients/${clientId}/messages`, fd));
      text.value = '';
      await refresh(false);
    } catch (e) {
      toast(e.message || friendly(e), true);
    }
  }

  photoInput.addEventListener('change', () => {
    const f = photoInput.files && photoInput.files[0];
    photoInput.value = '';
    if (f) sendFile(f, 'photo');
  });
  voiceInput.addEventListener('change', () => {
    const f = voiceInput.files && voiceInput.files[0];
    voiceInput.value = '';
    if (f) sendFile(f, 'voice');
  });

  const recBtn = composer.querySelector('#chat-rec-btn');
  if (recBtn && navigator.mediaDevices && window.MediaRecorder) {
    recBtn.addEventListener('click', async () => {
      if (recorder && recorder.state === 'recording') {
        recorder.stop();
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recordChunks = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (e) => {
          if (e.data.size) recordChunks.push(e.data);
        };
        recorder.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          recBtn.classList.remove('danger');
          const blob = new Blob(recordChunks, { type: 'audio/webm' });
          await sendFile(new File([blob], 'voice.webm', { type: 'audio/webm' }), 'voice');
        };
        recorder.start();
        recBtn.classList.add('danger');
        toast('Запись… нажмите ещё раз, чтобы остановить');
      } catch {
        toast('Микрофон недоступен — загрузите файл', true);
      }
    });
  } else if (recBtn) {
    recBtn.disabled = true;
    recBtn.title = 'Запись недоступна';
  }

  let lastCount = 0;

  async function refresh(scrollEnd) {
    try {
      const [clientsRes, msgRes] = await Promise.all([
        api.get('/manager/chat/clients?limit=50'),
        api.get(`/manager/chat/clients/${clientId}/messages?limit=80`),
      ]);
      clientMeta = (clientsRes.items || []).find((c) => c.id === clientId);
      const title = document.getElementById('chat-head-title');
      if (title && clientMeta) {
        title.replaceChildren(h('h1', null, clientMeta.name), clientMeta.telegram_unreachable ? h('p', { class: 'small warn' }, 'Клиент недоступен в Telegram') : null);
      }
      const messages = msgRes.messages || [];
      feed.replaceChildren(...messages.map(renderBubble));
      if (scrollEnd !== false && messages.length !== lastCount) {
        feed.scrollTop = feed.scrollHeight;
      }
      lastCount = messages.length;
      if (clientMeta && !clientMeta.can_write) {
        text.disabled = true;
      }
    } catch (e) {
      toast(friendly(e), true);
    }
  }

  await refresh();
  pollTimer = setInterval(() => refresh(true), POLL_MS);

  root.cleanup = () => {
    if (pollTimer) clearInterval(pollTimer);
    if (recorder && recorder.state === 'recording') recorder.stop();
  };

  return root;
}