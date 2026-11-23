import { api, friendly } from '../api.js';
import { isTelegramWebApp } from '../telegram.js';
import { brandMark, h, icon } from '../util.js';
import { loadMe, store } from '../store.js';
import { toast } from '../ui.js';

const DEMO = [
  { label: 'Управляющий', id: 100001, name: 'Иван' },
  { label: 'Мастер', id: 100002, name: 'Мастер' },
  { label: 'Клиент', id: 200001, name: 'Анна' },
];

/** Telegram-via-bot login: shows steps, polls until the bot confirms the one-time code. */
export function loginPanel({ onSuccess, compact = false }) {
  if (isTelegramWebApp()) {
    return h('div', { class: 'col' }, h('p', { class: 'muted' }, 'Вход через Telegram…'));
  }
  const root = h('div', { class: 'col' });
  let timer = null;
  let stopped = false;

  const stop = () => {
    stopped = true;
    if (timer) clearInterval(timer);
  };

  async function finish() {
    stop();
    await loadMe();
    toast('Вы вошли');
    onSuccess();
  }

  async function start(button) {
    button.disabled = true;
    try {
      const { code, telegram_go: goPath, bot_url: botUrl } = await api.post('/auth/start');
      if (!goPath && !botUrl) {
        toast('Бот ещё не подключён к этому бизнесу', true);
        button.disabled = false;
        return;
      }
      stopped = false;
      const tgOpen = goPath || botUrl;
      const link = h('a', { class: 'btn primary block', href: tgOpen, target: '_blank', rel: 'noopener' }, icon('send'), 'Открыть Telegram');
      const status = h('p', { class: 'small muted' }, '');
      status.textContent =
        'Это нормально: на экране Barber нажмите синюю кнопку START BOT. '
        + 'Если заходили в бота из поиска без сайта — сначала снова «Войти» здесь.';
      root.replaceChildren(link, status);
      window.open(tgOpen, '_blank', 'noopener');
      let ticks = 0;
      timer = setInterval(async () => {
        if (stopped) return;
        ticks += 1;
        try {
          const res = await api.get(`/auth/poll?code=${encodeURIComponent(code)}`);
          if (res.state === 'confirmed') await finish();
          else if (res.state === 'expired' || ticks > 150) {
            stop();
            status.textContent = 'Время ожидания истекло. Обновите страницу и попробуйте снова.';
          }
        } catch (e) {
          stop();
          status.textContent = friendly(e);
        }
      }, 2000);
    } catch (e) {
      toast(friendly(e), true);
      button.disabled = false;
    }
  }

  const go = h('button', { class: 'btn primary block', type: 'button' }, icon('send'), 'Войти через Telegram');
  go.addEventListener('click', () => start(go));
  root.append(go);

  if (!compact) {
    root.append(
      h(
        'div',
        { class: 'steps-list' },
        h('div', null, '1. Откроется бот нашего салона в Telegram.'),
        h('div', null, '2. В чате нажмите кнопку Start внизу (не команду /start из меню).'),
        h('div', null, '3. Вернитесь в браузер: вход подтвердится сам.'),
      ),
    );
  }

  if (store.info && store.info.dev_login) {
    const idInput = h('input', { class: 'input', type: 'number', placeholder: 'Telegram ID', inputmode: 'numeric' });
    const devLogin = async (id, name) => {
      try {
        await api.post('/auth/dev', { telegram_user_id: Number(id), name });
        await finish();
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

  root.cleanup = stop;
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
