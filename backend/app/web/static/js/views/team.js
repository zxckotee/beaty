import { api, friendly } from '../api.js';
import { duration, h, hueFor, icon, initials, money, plural } from '../util.js';
import { avatar, emptyState, field, openSheet, photoPicker, spinner, toast, withBusy } from '../ui.js';

export async function teamView({ embedded = false } = {}) {
  const root = h('section', { class: embedded ? 'dash-section' : 'dash-section-standalone', ...(embedded ? { id: 'dash-team' } : {}) });
  const list = h('div');
  const titleTag = embedded ? 'h2' : 'h1';
  let staff = [];
  let services = [];

  root.append(
    h(
      'div',
      { class: 'page-head' },
      h('div', null, h(titleTag, null, 'Специалисты'), h('p', null, 'Карточки мастеров: фото, описание и услуги, которые они выполняют.')),
      h('button', { class: 'btn primary', type: 'button', onclick: () => openForm(null) }, icon('plus'), 'Добавить'),
    ),
    list,
  );
  list.append(spinner());

  async function reload() {
    [staff, services] = await Promise.all([api.get('/manager/staff'), api.get('/manager/services')]);
    draw();
  }

  function draw() {
    if (!staff.length) {
      list.replaceChildren(emptyState('💇', 'Пока нет специалистов', 'Добавьте первого мастера, чтобы создавать для него ячейки.', h('button', { class: 'btn primary', type: 'button', onclick: () => openForm(null) }, 'Добавить специалиста')));
      return;
    }
    const cards = h('div', { class: 'cards' });
    for (const s of staff) {
      const cover = h('div', { class: 'cover', style: { '--h': hueFor(s.name) } }, initials(s.name));
      if (s.photo_url) cover.append(h('img', { src: s.photo_url, alt: s.name, loading: 'lazy' }));
      if (!s.is_active) cover.append(h('span', { class: 'chip warn badge-off' }, 'Скрыт'));
      const n = s.services.length;
      const body = h(
        'div',
        { class: 'body' },
        h('h3', null, s.name),
        s.specialization ? h('div', { class: 'small', style: { color: 'var(--accent)', fontWeight: 650 } }, s.specialization) : null,
        s.bio ? h('p', { class: 'small muted clamp2' }, s.bio) : null,
        h('div', { class: 'chips', style: { marginTop: 'auto' } }, h('span', { class: 'chip' }, n ? `${n} ${plural(n, 'услуга', 'услуги', 'услуг')}` : 'Все услуги')),
        h(
          'div',
          { class: 'row', style: { marginTop: '10px', gap: '8px' } },
          h('button', { class: 'btn sm', type: 'button', onclick: (e) => { e.stopPropagation(); location.hash = `#/team-schedule/${s.id}`; } }, icon('calendar'), 'График'),
        ),
      );
      cards.append(
        h(
          'button',
          { class: 'card pcard', type: 'button', onclick: () => openForm(s) },
          cover,
          body,
        ),
      );
    }
    cards.append(h('button', { class: 'add-card', type: 'button', onclick: () => openForm(null) }, icon('plus'), 'Новый специалист'));
    list.replaceChildren(cards);
  }

  function openForm(member) {
    const editing = Boolean(member);
    const links = new Map((member ? member.services : []).map((l) => [l.service_id, l]));
    openSheet({
      title: editing ? 'Карточка специалиста' : 'Новый специалист',
      build: (sheet) => {
        const photo = photoPicker({ url: member && member.photo_url, name: member ? member.name : 'Новый' });
        const name = h('input', { class: 'input', type: 'text', maxlength: '255', required: true, value: member ? member.name : '', placeholder: 'Имя' });
        const spec = h('input', { class: 'input', type: 'text', maxlength: '512', value: member ? member.specialization || '' : '', placeholder: 'Например, барбер, мастер маникюра' });
        const bio = h('textarea', { class: 'textarea', maxlength: '4000', placeholder: 'Несколько слов о мастере' }, member ? member.bio || '' : '');
        const active = h('input', { class: 'check', type: 'checkbox', checked: member ? member.is_active : true });
        const error = h('p', { class: 'small', style: { color: 'var(--bad)' }, role: 'alert' });

        const rows = services
          .filter((s) => s.is_active || links.has(s.id))
          .map((svc) => {
            const link = links.get(svc.id);
            const on = h('input', { class: 'check', type: 'checkbox', checked: Boolean(link), 'aria-label': svc.name });
            const price = h('input', { class: 'input', type: 'number', min: '0', step: '50', placeholder: String(svc.price_cents / 100), value: link && link.price_cents != null ? link.price_cents / 100 : '', 'aria-label': `Цена: ${svc.name}` });
            const dur = h('input', { class: 'input', type: 'number', min: '5', max: '720', step: '5', placeholder: String(svc.duration_minutes), value: link && link.duration_minutes ? link.duration_minutes : '', 'aria-label': `Минуты: ${svc.name}` });
            const row = h('div', { class: `link-row ${link ? '' : 'off'}` }, on, h('div', null, h('div', { style: { fontWeight: 600 } }, svc.name), h('div', { class: 'tiny muted' }, `${money(svc.price_cents)} · ${duration(svc.duration_minutes)}`)), price, dur);
            on.addEventListener('change', () => row.classList.toggle('off', !on.checked));
            return { svc, on, price, dur, row };
          });

        sheet.body.append(
          photo.el,
          field('Имя', name),
          field('Специализация', spec),
          field('О специалисте', bio),
          h(
            'div',
            { class: 'col', style: { gap: '4px' } },
            h('span', { class: 'label' }, 'Услуги специалиста'),
            h('span', { class: 'tiny muted' }, 'Отметьте услуги. Справа можно задать свою цену (₽) и длительность (мин) для этого мастера.'),
            rows.length ? rows.map((r) => r.row) : h('p', { class: 'small muted' }, 'Сначала создайте услуги.'),
          ),
          editing ? h('label', { class: 'row' }, active, 'Показывать клиентам') : null,
          error,
        );

        const save = h('button', { class: 'btn primary', type: 'button' }, editing ? 'Сохранить' : 'Создать');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            error.textContent = '';
            if (!name.value.trim()) {
              error.textContent = 'Укажите имя.';
              return;
            }
            const payload = {
              display_name: name.value.trim(),
              specialization: spec.value.trim() || null,
              bio: bio.value.trim() || null,
              services: rows.filter((r) => r.on.checked).map((r) => ({
                service_id: r.svc.id,
                price_cents: r.price.value === '' ? null : Math.round(Number(r.price.value) * 100),
                duration_minutes: r.dur.value === '' ? null : Number(r.dur.value),
              })),
            };
            try {
              let saved;
              if (editing) {
                saved = await api.patch(`/manager/staff/${member.id}`, { ...payload, is_active: active.checked });
              } else {
                saved = await api.post('/manager/staff', payload);
              }
              const file = photo.getFile();
              if (file) {
                const withPhoto = await api.upload(`/manager/staff/${saved.id}/photo`, file);
                if (withPhoto.photo_url) photo.setServerUrl(`${withPhoto.photo_url}?t=${Date.now()}`);
              }
              sheet.close();
              toast(editing ? 'Карточка сохранена' : 'Специалист добавлен');
              reload();
            } catch (e) {
              error.textContent = friendly(e);
            }
          }),
        );
        sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), save);
      },
    });
  }

  try {
    await reload();
  } catch (e) {
    list.replaceChildren(emptyState('⚠️', 'Не удалось загрузить', friendly(e)));
  }
  return root;
}
