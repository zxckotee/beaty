import { api, friendly } from '../api.js';
import { duration, h, icon, longDayLabel, money } from '../util.js';
import { avatar, emptyState, field, openSheet, toast, withBusy } from '../ui.js';

const STATUS = {
  booked: ['Записан', 'ok'],
  confirmed: ['Подтверждён', 'ok'],
  held: ['Ожидает', 'warn'],
  arrived: ['Пришёл', 'ok'],
  completed: ['Завершён', ''],
  cancelled: ['Отменён', 'bad'],
  no_show: ['Не пришёл', 'bad'],
};

export async function mineView() {
  const root = h('div');
  const list = h('div', { class: 'list' });
  root.append(h('div', { class: 'page-head' }, h('div', null, h('h1', null, 'Мои записи'), h('p', null, 'Предстоящие и прошедшие визиты.'))), list);

  async function reload() {
    const rows = await api.get('/client/bookings');
    if (!rows.length) {
      list.replaceChildren(emptyState('📅', 'Записей пока нет', 'Выберите услугу и подходящее время.', h('a', { class: 'btn primary', href: '#/book' }, 'Записаться')));
      return;
    }
    const upcoming = rows.filter((r) => r.upcoming).reverse();
    const past = rows.filter((r) => !r.upcoming);
    list.replaceChildren(
      upcoming.length ? h('h2', null, 'Предстоящие') : null,
      ...upcoming.map((r) => card(r, true)),
      past.length ? h('h2', { style: { marginTop: '10px' } }, 'История') : null,
      ...past.map((r) => card(r, false)),
    );
  }

  function card(b, cancellable) {
    const [label, tone] = STATUS[b.status] || [b.status, ''];
    return h(
      'article',
      { class: 'card pad col' },
      h('div', { class: 'row between' }, h('b', null, `${longDayLabel(b.date)}, ${b.start}–${b.end}`), h('span', { class: `chip ${tone}` }, label)),
      h('div', { class: 'row' }, avatar(b.staff), h('div', { class: 'grow' }, h('b', null, b.staff.name), h('div', { class: 'small muted' }, b.services.map((s) => `${s.name} · ${duration(s.duration_minutes)}`).join(', ')))),
      h(
        'div',
        { class: 'row between' },
        h('b', null, money(b.total_price_cents)),
        cancellable
          ? h('button', { class: 'btn sm danger', type: 'button', onclick: () => cancel(b) }, icon('close'), 'Отменить')
          : null,
      ),
    );
  }

  function cancel(b) {
    openSheet({
      title: 'Отменить запись?',
      build: (sheet) => {
        const note = field({ label: 'Причина отмены', tag: 'textarea', props: { rows: 3, maxlength: 500, placeholder: 'Например: заболел, не получается приехать' } });
        sheet.body.append(
          h('p', { class: 'muted small' }, `${longDayLabel(b.date)}, ${b.start}. Время освободится для других клиентов.`),
          note.el,
        );
        const foot = h('div', { class: 'row wrap', style: { gap: '8px', justifyContent: 'flex-end', width: '100%' } });
        foot.append(
          h('button', { class: 'btn ghost', type: 'button', onclick: () => sheet.close() }, 'Назад'),
          h(
            'button',
            {
              class: 'btn danger',
              type: 'button',
              onclick: () => withBusy(foot, async () => {
                const reason = note.input.value.trim();
                if (!reason) {
                  toast('Укажите причину отмены', true);
                  return;
                }
                try {
                  await api.post(`/client/bookings/${b.id}/cancel`, { reason });
                  toast('Запись отменена');
                  sheet.close();
                  await reload();
                } catch (e) {
                  toast(friendly(e), true);
                }
              }),
            },
            icon('close'),
            'Отменить запись',
          ),
        );
        sheet.setFooter(foot);
      },
    });
  }

  await reload();
  return root;
}
