import { applyTheme, resolveInitialTheme, themeToggleButton } from './theme.js';

const TG_PLATFORM = 'https://t.me/beaty_welcome_agent';
const DEFAULT_PLATFORM_BOT = 'beaty_welcome_agent';

async function platformTelegramLogin(user) {
  const res = await fetch('/api/platform/auth/telegram-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(user),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = typeof detail === 'string' ? detail : 'Не удалось войти';
    throw new Error(msg);
  }
  if (data.state === 'no_tenant' && data.message) {
    alert(data.message);
  }
  if (data.redirect) {
    window.location.href = data.redirect;
    return;
  }
  throw new Error('Нет адреса для перехода');
}

function mountTelegramLoginWidget(container, botUsername) {
  const script = document.createElement('script');
  script.async = true;
  script.src = 'https://telegram.org/js/telegram-widget.js?22';
  script.setAttribute('data-telegram-login', botUsername);
  script.setAttribute('data-size', 'medium');
  script.setAttribute('data-userpic', 'false');
  script.setAttribute('data-request-access', 'write');
  script.setAttribute('data-onauth', 'onPlatformTelegramAuth(user)');
  container.replaceChildren(script);
}

function appendDocsSection(root, section, openByDefault) {
  const det = document.createElement('details');
  det.className = 'platform-details';
  if (openByDefault) det.open = true;
  const summary = document.createElement('summary');
  summary.textContent = section.title;
  const body = document.createElement('div');
  body.className = 'platform-details-body';
  const p = document.createElement('p');
  p.textContent = section.body;
  body.append(p);
  det.append(summary, body);
  root.append(det);
}

async function loadPlatformDocsPage() {
  const sectionsRoot = document.getElementById('docs-sections');
  const legalRoot = document.getElementById('docs-legal');
  if (!sectionsRoot) return;
  try {
    const data = await fetch('/api/docs/platform').then((r) => {
      if (!r.ok) throw new Error('load failed');
      return r.json();
    });
    sectionsRoot.replaceChildren();
    for (const s of data.sections || []) {
      appendDocsSection(sectionsRoot, s, s.id === 'platform-onboard');
    }
    if (legalRoot) {
      legalRoot.replaceChildren();
      for (const link of data.legal_links || []) {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = link.href;
        a.textContent = link.label;
        li.append(a);
        legalRoot.append(li);
      }
    }
  } catch {
    sectionsRoot.replaceChildren(
      Object.assign(document.createElement('p'), {
        className: 'muted',
        textContent: 'Не удалось загрузить разделы. Обновите страницу.',
      }),
    );
  }
}

function telegramLoginFallbackLink() {
  return Object.assign(document.createElement('a'), {
    className: 'btn btn-telegram',
    href: TG_PLATFORM,
    target: '_blank',
    rel: 'noopener',
    textContent: 'Войти через Telegram',
  });
}

async function mountPlatformTelegramLoginWidgets(loginMounts) {
  try {
    const cfg = await fetch('/api/platform/telegram-login-config').then((r) => r.json());
    const botUsername = cfg.bot_username ? String(cfg.bot_username) : DEFAULT_PLATFORM_BOT;
    for (const loginMount of loginMounts) {
      if (cfg.enabled && botUsername) {
        mountTelegramLoginWidget(loginMount, botUsername);
      } else {
        loginMount.replaceChildren(telegramLoginFallbackLink());
      }
    }
  } catch {
    for (const loginMount of loginMounts) {
      loginMount.replaceChildren(telegramLoginFallbackLink());
    }
  }
}

async function boot() {
  applyTheme(resolveInitialTheme());
  const cta = document.querySelector('.platform-nav-cta');
  if (cta) cta.insertBefore(themeToggleButton(), cta.firstChild);

  const demoLinks = document.querySelectorAll('[data-demo-link]');
  const tgLinks = document.querySelectorAll('[data-tg-platform]');
  const loginMounts = document.querySelectorAll('[data-tg-login-widget]');

  for (const el of tgLinks) {
    el.href = TG_PLATFORM;
  }

  window.onPlatformTelegramAuth = (user) => {
    platformTelegramLogin(user).catch((err) => {
      alert(err.message || 'Не удалось войти через Telegram');
    });
  };

  try {
    const meta = await fetch('/api/platform').then((r) => r.json());
    const demoId = meta.demo_tenant_id;
    if (demoId) {
      const href = `/t/${encodeURIComponent(demoId)}/`;
      for (const el of demoLinks) {
        el.hidden = false;
        el.href = href;
        if (el.textContent.trim() === 'Попробовать демо') {
          el.textContent = 'Открыть демо-кабинет';
        }
      }
    }
  } catch {
    /* static page still works */
  }

  if (loginMounts.length) {
    await mountPlatformTelegramLoginWidgets(loginMounts);
  }

  await loadPlatformDocsPage();
}

boot();