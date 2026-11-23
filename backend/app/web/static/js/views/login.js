import { api, friendly } from '../api.js';
import { isMessengerWebApp } from '../messenger.js';
import { brandMark, h, icon } from '../util.js';
import { loadMe, store } from '../store.js';
import { toast } from '../ui.js';

const DEMO = [
  { label: 'Управляющий', id: 100001, name: 'Иван' },
  { label: 'Мастер', id: 100002, name: 'Мастер' },
  { label: 'Клиент', id: 200001, name: 'Анна' },
];

function loginFlow(root, { goPath, code, label, openHint }) {
  let timer = null;
  let stopped = false;
  const stop = () => {
    stopped = true;
    if (timer) clearInterval(timer);
  };
  const status = h('p', { class: 'small muted' }, openHint);
  const link = h('a', { class: 'btn primary block', href: goPath, target: '_blank', rel: 'noopener' }, icon('send'), `Открыть ${label}`);
  root.replaceChildren(link, status);
  window.open(goPath, '_blank', 'noopener');
  let ticks = 0;
  timer = setInterval(async () => {
    if (stopped) return;
    ticks += 1;
    try {
      const res = await api.get(`/auth/poll?code=${encodeURIComponent(code)}`);
      if (res.state === 'confirmed') {
        stop();
        await loadMe();
        toast('Вы вошли');
        return 'done';
      }
      if (res.state === 'expired' || ticks > 150) {
        stop();
        status.textContent = 'Время ожидания истекло. Получите новую ссылку.';
      }
    } catch (e) {
      stop();
      status.textContent = friendly(e);
    }
  }, 2000);
  return stop;
}

/** Browser login via Telegram or MAX bot deep link. */
export function loginPanel({ onSuccess, compact = false }) {
  if (isMessengerWebApp()) {
    return h('div', { class: 'col' }, h('p', { class: 'muted' }, 'Вход через мессенджер…'));
  }
  const root = h('div', { class: 'col' });
  let cleanup = null;

  async function start(button, channel) {
    button.disabled = true;
    try {
      const data = await api.post('/auth/start');
      const code = data.code;
      const goPath = channel === 'max' ? data.max_go || data.max_bot_url : data.telegram_go || data.bot_url;
      if (!goPath) {
        toast(channel === 'max' ? 'MAX-бот не подключён' : 'Telegram-бот не подключён', true);
        button.disabled = false;
        return;
      }
      if (cleanup) cleanup();
      cleanup = loginFlow(root, {
        goPath,
        code,
        label: channel === 'max' ? 'MAX' : 'Telegram',
        openHint:
          channel === 'max'
            ? 'В MAX откройте диалог с ботом и подтвердите старт.'
            : 'В Telegram нажмите Start у бота салона.',
      });
      const check = setInterval(async () => {
        const me = store.me;
        if (me && me.authenticated) {
          clearInterval(check);
          if (cleanup) cleanup();
          onSuccess();
        }
      }, 2500);
    } catch (e) {
      toast(friendly(e), true);
      button.disabled = false;
    }
  }

  const tg = h('button', { class: 'btn primary block', type: 'button' }, icon('send'), 'Войти через Telegram');
  tg.addEventListener('click', () => start(tg, 'telegram'));
  const mx = h('button', { class: 'btn block', type: 'button' }, icon('max'), 'Войти через MAX');
  mx.addEventListener('click', () => start(mx, 'max'));
  root.append(tg, mx);

  if (!compact) {
    root.append(
      h(
        'div',
        { class: 'steps-list' },
        h('div', null, '1. Выберите мессенджер, где у вас есть бот салона.'),
        h('div', null, '2. Подтвердите старт в чате с ботом.'),
        h('div', null, '3. Вернитесь в браузер — вход подтвердится автоматически.'),
      ),
    );
  }

  if (store.info && store.info.dev_login) {
    const idInput = h('input', { class: 'input', type: 'number', placeholder: 'Telegram ID', inputmode: 'numeric' });
    const devLogin = async (id, name) => {
      try {
        await api.post('/auth/dev', { telegram_user_id: Number(id), name });
        await loadMe();
        toast('Вы вошли');
        onSuccess();
      } catch (e) {
        toast(friendly(e), true);
      }
    };
    root.append(
      h(
        'details',
        null,
        h('summary', null, 'Демо-вход (только для разработки)'),
        h(
          'div',
          { class: 'col', style: { marginTop: '10px' } },
          h('div', { class: 'chips' }, DEMO.map((d) => h('button', { class: 'chip', type: 'button', onclick: () => devLogin(d.id, d.name) }, `${d.label} · ${d.id}`))),
          h('div', { class: 'row' }, idInput, h('button', { class: 'btn', type: 'button', onclick: () => idInput.value && devLogin(idInput.value, 'Гость') }, 'Войти')),
        ),
      ),
    );
  }

  root.cleanup = () => {
    if (cleanup) cleanup();
  };
  return root;
}

export function loginView(onSuccess) {
  const panel = loginPanel({ onSuccess });
  const name = store.info ? store.info.name : '';
  const el = h(
    'div',
    { class: 'card login' },
    brandMark(store.info),
    h('div', null, h('h1', null, 'Вход'), h('p', { class: 'muted', style: { marginTop: '6px' } }, `Войдите, чтобы записываться и управлять записями в «${name}».`)),
    panel,
  );
  el.cleanup = panel.cleanup;
  return el;
}