import { api, friendly } from '../api.js';
import { duration, h, hueFor, icon, initials, money } from '../util.js';
import { emptyState, field, openSheet, photoPicker, spinner, toast, withBusy } from '../ui.js';

export async function servicesView() {
  const root = h('div');
  const list = h('div');
  let services = [];

  root.append(
    h(
      'div',
      { class: 'page-head' },
      h('div', null, h('h1', null, 'Услуги'), h('p', null, 'Карточки услуг: цена, стандартная длительность и описание.')),
      h('button', { class: 'btn primary', type: 'button', onclick: () => openForm(null) }, icon('plus'), 'Добавить'),
    ),
    list,
  );
  list.append(spinner());

  async function reload() {
    services = await api.get('/manager/services');
    draw();
  }

  function draw() {
    if (!services.length) {
      list.replaceChildren(emptyState('✂️', 'Каталог пуст', 'Добавьте услуги, которые клиенты смогут выбирать при записи.', h('button', { class: 'btn primary', type: 'button', onclick: () => openForm(null) }, 'Добавить услугу')));
      return;
    }
    const cards = h('div', { class: 'cards' });
    for (const s of services) {
      const cover = h('div', { class: 'cover', style: { '--h': hueFor(s.name) } }, initials(s.name));
      if (s.photo_url) cover.append(h('img', { src: s.photo_url, alt: s.name, loading: 'lazy' }));
      if (!s.is_active) cover.append(h('span', { class: 'chip warn badge-off' }, 'В архиве'));
      cards.append(
        h(
          'button',
          { class: 'card pcard', type: 'button', onclick: () => openForm(s) },
          cover,
          h(
            'div',
            { class: 'body' },
            h('h3', null, s.name),
            s.description ? h('p', { class: 'small muted clamp2' }, s.description) : null,
            h('div', { class: 'row between', style: { marginTop: 'auto' } }, h('span', { class: 'price' }, money(s.price_cents)), h('span', { class: 'chip' }, icon('clock'), duration(s.duration_minutes))),
          ),
        ),
      );
    }
    cards.append(h('button', { class: 'add-card', type: 'button', onclick: () => openForm(null) }, icon('plus'), 'Новая услуга'));
    list.replaceChildren(cards);
  }

  function openForm(service) {
    const editing = Boolean(service);
    openSheet({
      title: editing ? 'Карточка услуги' : 'Новая услуга',
      build: (sheet) => {
        const photo = photoPicker({ url: service && service.photo_url, name: service ? service.name : 'Услуга', square: true });
        const name = h('input', { class: 'input', type: 'text', maxlength: '255', required: true, value: service ? service.name : '', placeholder: 'Название услуги' });
        const price = h('input', { class: 'input', type: 'number', min: '0', step: '50', inputmode: 'decimal', value: service ? service.price_cents / 100 : '', placeholder: '1500' });
        const dur = h('input', { class: 'input', type: 'number', min: '5', max: '720', step: '5', inputmode: 'numeric', value: service ? service.duration_minutes : 60 });
        const buffer = h('input', { class: 'input', type: 'number', min: '0', max: '240', step: '5', inputmode: 'numeric', value: service ? service.buffer_minutes : 0 });
        const desc = h('textarea', { class: 'textarea', maxlength: '4000', placeholder: 'Что входит в услугу' }, service ? service.description || '' : '');
        const active = h('input', { class: 'check', type: 'checkbox', checked: service ? service.is_active : true });
        const error = h('p', { class: 'small', style: { color: 'var(--bad)' }, role: 'alert' });
        const quick = h('div', { class: 'chips' }, [15, 30, 45, 60, 90, 120].map((m) => h('button', { class: 'chip', type: 'button', onclick: () => { dur.value = m; } }, duration(m))));

        sheet.body.append(
          photo.el,
          field('Название', name),
          h('div', { class: 'grid2' }, field('Цена, ₽', price), field('Длительность, мин', dur)),
          quick,
          field('Буфер после услуги, мин', buffer, 'Время на уборку и подготовку: учитывается в расписании мастера.'),
          field('Описание', desc),
          editing ? h('label', { class: 'row' }, active, 'Доступна для записи') : null,
          error,
        );

        const save = h('button', { class: 'btn primary', type: 'button' }, editing ? 'Сохранить' : 'Создать');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            error.textContent = '';
            const payload = {
              name: name.value.trim(),
              price_cents: Math.round(Number(price.value || 0) * 100),
              duration_minutes: Number(dur.value),
              buffer_minutes: Number(buffer.value || 0),
              description: desc.value.trim() || null,
            };
            if (!payload.name) {
              error.textContent = 'Укажите название.';
              return;
            }
            if (!(payload.duration_minutes >= 5)) {
              error.textContent = 'Длительность — не меньше 5 минут.';
              return;
            }
            try {
              const saved = editing ? await api.patch(`/manager/services/${service.id}`, { ...payload, is_active: active.checked }) : await api.post('/manager/services', payload);
              const file = photo.getFile();
              if (file) await api.upload(`/manager/services/${saved.id}/photo`, file);
              sheet.close();
              toast(editing ? 'Услуга сохранена' : 'Услуга добавлена');
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
