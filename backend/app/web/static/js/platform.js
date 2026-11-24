import { applyTheme, resolveInitialTheme, themeToggleButton } from './theme.js';

async function boot() {
  applyTheme(resolveInitialTheme());
  const cta = document.querySelector('.platform-nav-cta');
  if (cta) cta.insertBefore(themeToggleButton(), cta.firstChild);

  const demoLinks = document.querySelectorAll('[data-demo-link]');
  const tgLink = document.querySelector('[data-tg-platform]');
  const hint = document.querySelector('[data-platform-hint]');

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
      if (hint) hint.hidden = true;
    }
  } catch {
    /* static page still works */
  }

  if (tgLink) {
    tgLink.href = 'https://t.me/';
    tgLink.hidden = false;
  }
}

boot();