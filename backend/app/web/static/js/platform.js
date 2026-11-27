import { applyTheme, resolveInitialTheme, themeToggleButton } from './theme.js';

const TG_PLATFORM = 'https://t.me/beaty_welcome_agent';

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

async function boot() {
  applyTheme(resolveInitialTheme());
  const cta = document.querySelector('.platform-nav-cta');
  if (cta) cta.insertBefore(themeToggleButton(), cta.firstChild);

  const demoLinks = document.querySelectorAll('[data-demo-link]');
  const tgLinks = document.querySelectorAll('[data-tg-platform]');
  const loginMount = document.querySelector('[data-tg-login-widget]');

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

  if (loginMount) {
    try {
      const cfg = await fetch('/api/platform/telegram-login-config').then((r) => r.json());
      if (cfg.enabled && cfg.bot_username) {
        mountTelegramLoginWidget(loginMount, cfg.bot_username);
      } else {
        loginMount.replaceChildren(
          Object.assign(document.createElement('a'), {
            className: 'btn btn-telegram',
            href: TG_PLATFORM,
            target: '_blank',
            rel: 'noopener',
            textContent: 'Войти через Telegram',
          }),
        );
      }
    } catch {
      loginMount.replaceChildren(
        Object.assign(document.createElement('a'), {
          className: 'btn btn-telegram',
          href: TG_PLATFORM,
          target: '_blank',
          rel: 'noopener',
          textContent: 'Войти через Telegram',
        }),
      );
    }
  }
}

boot();