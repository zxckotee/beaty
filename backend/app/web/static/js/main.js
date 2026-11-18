import { api, friendly, tenantId } from './api.js';
import { clear, h, icon } from './util.js';
import { isManager, isSpecialist, loadInfo, loadMe, store } from './store.js';
import { toast } from './ui.js';
import { loginView } from './views/login.js';
import { dayView } from './views/day.js';
import { teamView } from './views/team.js';
import { servicesView } from './views/services.js';
import { bookView } from './views/book.js';
import { mineView } from './views/mine.js';
import { scheduleEditView } from './views/schedule-edit.js';

const app = document.getElementById('app');
let cleanup = null;
let renderToken = 0;

const NAV = {
  manager: [
    { route: 'day', label: 'Расписание', icon: 'calendar' },
    { route: 'team', label: 'Специалисты', icon: 'users' },
    { route: 'services', label: 'Услуги', icon: 'scissors' },
  ],
  specialist: [{ route: 'day', label: 'Мой день', icon: 'calendar' }],
  client: [
    { route: 'book', label: 'Запись', icon: 'scissors' },
    { route: 'mine', label: 'Мои записи', icon: 'list' },
  ],
};

const ROUTES = {
  day: { roles: ['manager', 'specialist'], view: () => dayView({ manager: isManager() }) },
  team: { roles: ['manager'], view: () => teamView() },
  'team-schedule': { roles: ['manager'], view: (sub) => scheduleEditView(sub) },
  services: { roles: ['manager'], view: () => servicesView() },
  book: { roles: ['client'], view: (sub) => bookView(sub) },
  mine: { roles: ['client'], needsAuth: true, view: () => mineView() },
  login: { roles: ['client', 'manager', 'specialist'], view: () => loginView(() => navigate(defaultRoute())) },
};

const activeRole = () => (store.me.authenticated ? store.me.active_role : 'client');
const defaultRoute = () => (activeRole() === 'client' ? 'book' : 'day');

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [route, sub] = raw.split('/');
  return { route: route || defaultRoute(), sub: sub || '' };
}

export function navigate(route) {
  if (location.hash === `#/${route}`) render();
  else location.hash = `#/${route}`;
}

function applyBrand() {
  const color = store.info && store.info.brand && store.info.brand.primary;
  if (typeof color === 'string' && /^#[0-9a-fA-F]{6}$/.test(color)) {
    document.documentElement.style.setProperty('--brand', color);
    document.querySelector('meta[name=theme-color]').setAttribute('content', color);
  }
  document.title = store.info ? `${store.info.name} · запись онлайн` : 'Запись онлайн';
}

function header(route) {
  const items = NAV[activeRole()] || NAV.client;
  const me = store.me;
  const nav = h(
    'nav',
    { class: 'nav-top', 'aria-label': 'Разделы' },
    items.map((i) => h('a', { href: `#/${i.route}`, class: route === i.route ? 'active' : '' }, i.label)),
  );
  const right = h('div', { class: 'row' });
  if (me.authenticated) {
    if (me.roles.length > 1) {
      const select = h('select', { class: 'select', style: { minHeight: '38px', padding: '4px 10px', width: 'auto', borderRadius: '999px', fontWeight: 650 }, 'aria-label': 'Роль' });
      for (const r of me.roles) select.append(h('option', { value: r.id, selected: r.id === me.active_role }, r.label));
      select.addEventListener('change', async () => {
        try {
          store.me = await api.post('/me/role', { role: select.value });
          navigate(defaultRoute());
        } catch (e) {
          toast(friendly(e), true);
        }
      });
      right.append(select);
    }
    right.append(
      h('button', { class: 'btn ghost icon-btn', type: 'button', title: `Выйти (${me.name})`, 'aria-label': 'Выйти', onclick: logout }, icon('logout')),
    );
  } else {
    right.append(h('a', { class: 'btn sm primary', href: '#/login' }, 'Войти'));
  }
  const name = store.info ? store.info.name : '';
  return h(
    'header',
    { class: 'header' },
    h('a', { class: 'brand', href: `#/${defaultRoute()}` }, h('div', { class: 'brand-mark' }, (name || 'B')[0].toUpperCase()), h('span', { class: 'brand-name' }, name)),
    nav,
    h('div', { class: 'header-spacer' }),
    right,
  );
}

function bottomNav(route) {
  const items = NAV[activeRole()] || NAV.client;
  return h(
    'nav',
    { class: 'nav-bottom', 'aria-label': 'Разделы' },
    items.map((i) => h('a', { href: `#/${i.route}`, class: route === i.route ? 'active' : '' }, icon(i.icon), h('span', null, i.label))),
  );
}

async function logout() {
  await api.post('/auth/logout');
  store.me = { authenticated: false };
  navigate('book');
}

async function render() {
  const token = ++renderToken;
  if (cleanup) {
    cleanup();
    cleanup = null;
  }
  let { route, sub } = parseHash();
  let def = ROUTES[route];
  if (!def || !def.roles.includes(activeRole())) {
    route = defaultRoute();
    def = ROUTES[route];
    history.replaceState(null, '', `#/${route}`);
  }
  if (def.needsAuth && !store.me.authenticated) {
    route = 'login';
    def = ROUTES.login;
  }
  const main = h('main', { class: 'main', id: 'main' });
  clear(app).append(h('div', { class: 'shell' }, header(route), main, bottomNav(route)));
  if (store.info && store.info.read_only) main.append(h('div', { class: 'banner' }, 'Подписка неактивна: сервис работает в режиме просмотра.'));
  try {
    const node = await def.view(sub);
    if (token !== renderToken) {
      if (node && node.cleanup) node.cleanup();
      return;
    }
    if (node) {
      main.append(node);
      cleanup = node.cleanup || null;
    }
  } catch (e) {
    if (token !== renderToken) return;
    if (e.status === 401) {
      store.me = { authenticated: false };
      navigate('login');
      return;
    }
    main.append(h('div', { class: 'empty card' }, h('div', { class: 'big' }, '⚠️'), h('h3', null, 'Не удалось загрузить'), h('p', null, friendly(e))));
  }
  window.scrollTo({ top: 0 });
}

async function boot() {
  if (!tenantId) {
    app.textContent = 'Откройте ссылку вашего салона.';
    return;
  }
  try {
    await loadInfo();
  } catch {
    app.append(h('div', { class: 'main' }, h('div', { class: 'empty card' }, h('div', { class: 'big' }, '🔍'), h('h3', null, 'Салон не найден'), h('p', null, 'Проверьте адрес ссылки.'))));
    return;
  }
  applyBrand();
  await loadMe();
  window.addEventListener('hashchange', render);
  render();
}

boot();
