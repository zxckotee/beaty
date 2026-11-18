import { api, friendly } from '../api.js';
import { h, icon, todayIn } from '../util.js';
import { store } from '../store.js';
import { confirmDialog, emptyState, field, openSheet, spinner, toast, withBusy } from '../ui.js';

export async function scheduleEditView(staffId) {
  const root = h('div');
  const body = h('div');
  root.append(
    h(
      'div',
      { class: 'page-head' },
      h('div', null, h('h1', null, 'График мастера'), h('p', { class: 'muted' }, 'Недельное расписание и исключения по датам.')),
      h('button', { class: 'btn sm', type: 'button', onclick: () => { location.hash = '#/team'; } }, icon('chevL'), 'К команде'),
    ),
    body,
  );
  body.append(spinner());

  let schedule = null;
  let exceptions = [];
  const from = todayIn(store.info.timezone);

  async function reload() {
    try {
      [schedule, exceptions] = await Promise.all([
        api.get(`/manager/staff/${staffId}/schedule`),
        api.get(`/manager/staff/${staffId}/exceptions?from=${from}&days=90`),
      ]);
      draw();
    } catch (e) {
      body.replaceChildren(emptyState('⚠️', 'Не удалось загрузить', friendly(e)));
    }
  }

  function draw() {
    const grid = h('div', { class: 'schedule-week' });
    for (const day of schedule.days) {
      const enabled = h('input', { class: 'check', type: 'checkbox', checked: day.enabled, 'aria-label': day.label });
      const start = h('input', { class: 'input', type: 'time', value: day.enabled ? toTimeInput(day.start_time) : '09:00' });
      const end = h('input', { class: 'input', type: 'time', value: day.enabled ? toTimeInput(day.end_time) : '18:00' });
      const toggle = () => {
        start.disabled = end.disabled = !enabled.checked;
      };
      enabled.addEventListener('change', toggle);
      toggle();
      grid.append(
        h(
          'div',
          { class: 'card schedule-day', 'data-wd': String(day.weekday) },
          h('label', { class: 'row between' }, h('b', null, day.label), enabled),
          h('div', { class: 'grid2' }, field('С', start), field('До', end)),
        ),
      );
    }

    const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить неделю');
    save.addEventListener('click', () =>
      withBusy(save, async () => {
        const days = [...grid.querySelectorAll('.schedule-day')].map((row) => {
          const wd = Number(row.dataset.wd);
          const enabled = row.querySelector('.check').checked;
          const inputs = row.querySelectorAll('input[type=time]');
          return {
            weekday: wd,
            enabled,
            start_time: fromTimeInput(inputs[0].value),
            end_time: fromTimeInput(inputs[1].value),
          };
        });
        try {
          schedule = await api.put(`/manager/staff/${staffId}/schedule`, { days });
          toast('График сохранён');
        } catch (e) {
          toast(friendly(e), true);
        }
      }),
    );

    const excList = h('div', { class: 'list' });
    for (const ex of exceptions.items || []) {
      const label = ex.kind === 'work_override' ? `Особые часы ${ex.date} ${ex.start}–${ex.end}` : `Выходной ${ex.date}`;
      excList.append(
        h(
          'div',
          { class: 'card row between' },
          h('div', null, h('b', null, label), ex.note ? h('div', { class: 'small muted' }, ex.note) : null),
          h('button', { class: 'btn sm ghost', type: 'button', onclick: () => removeExc(ex.id) }, icon('trash')),
        ),
      );
    }

    const addExc = h('div', { class: 'row wrap', style: { gap: '8px', marginTop: '12px' } });
    addExc.append(
      h('button', { class: 'btn sm', type: 'button', onclick: () => openDayOff() }, 'Выходной на дату'),
      h('button', { class: 'btn sm', type: 'button', onclick: () => openOverride() }, 'Особые часы'),
    );

    body.replaceChildren(
      h('h2', null, 'Неделя'),
      grid,
      save,
      h('h2', { style: { marginTop: '24px' } }, 'Исключения'),
      excList.children.length ? excList : h('p', { class: 'muted small' }, 'Нет исключений на ближайшие 90 дней.'),
      addExc,
    );
  }

  async function removeExc(id) {
    if (!(await confirmDialog('Удалить исключение?'))) return;
    try {
      await api.delete(`/manager/staff/${staffId}/exceptions/${id}`);
      toast('Удалено');
      await reload();
    } catch (e) {
      toast(friendly(e), true);
    }
  }

  function openDayOff() {
    const date = h('input', { class: 'input', type: 'date', value: from });
    const note = h('input', { class: 'input', type: 'text', maxlength: '500', placeholder: 'Комментарий' });
    openSheet({
      title: 'Выходной',
      build: (sheet) => {
        sheet.body.append(field('Дата', date), field('Комментарий', note));
        const ok = h('button', { class: 'btn primary', type: 'button' }, 'Добавить');
        ok.addEventListener('click', () =>
          withBusy(ok, async () => {
            try {
              await api.post(`/manager/staff/${staffId}/exceptions/day-off`, { date: date.value, note: note.value.trim() || null });
              sheet.close();
              toast('Выходной добавлен');
              await reload();
            } catch (e) {
              toast(friendly(e), true);
            }
          }),
        );
        sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), ok);
      },
    });
  }

  function openOverride() {
    const date = h('input', { class: 'input', type: 'date', value: from });
    const start = h('input', { class: 'input', type: 'time', value: '10:00' });
    const end = h('input', { class: 'input', type: 'time', value: '16:00' });
    openSheet({
      title: 'Особые часы',
      build: (sheet) => {
        sheet.body.append(field('Дата', date), field('Начало', start), field('Конец', end));
        const ok = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        ok.addEventListener('click', () =>
          withBusy(ok, async () => {
            try {
              await api.post(`/manager/staff/${staffId}/exceptions/work-override`, {
                date: date.value,
                start_time: fromTimeInput(start.value),
                end_time: fromTimeInput(end.value),
              });
              sheet.close();
              toast('Исключение сохранено');
              await reload();
            } catch (e) {
              toast(friendly(e), true);
            }
          }),
        );
        sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), ok);
      },
    });
  }

  await reload();
  return root;
}

function toTimeInput(hhmm) {
  if (hhmm === '24:00') return '23:59';
  return hhmm.length === 5 ? `${hhmm}:00`.slice(0, 5) : hhmm;
}

function fromTimeInput(value) {
  if (!value) return '09:00';
  const [h, m] = value.split(':');
  return `${h.padStart(2, '0')}:${m.padStart(2, '0')}`;
}