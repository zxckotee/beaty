import { api, friendly } from './api.js';
import { h, icon, normalizeTime24, readTimeInput, timeInput, todayIn } from './util.js';
import { store } from './store.js';
import { confirmDialog, field, openSheet, spinner, toast, withBusy } from './ui.js';

function toTimeInput(hhmm) {
  if (!hhmm) return '09:00';
  return hhmm === '24:00' ? '24:00' : (normalizeTime24(hhmm) || '09:00');
}

function fromTimeInput(value) {
  return normalizeTime24(value) || '09:00';
}

/**
 * @param {HTMLElement} mount
 * @param {string} staffId
 * @param {{ anchorDate?: string, onSaved?: () => void }} opts
 */
export async function mountScheduleEditor(mount, staffId, opts = {}) {
  const anchorDate = opts.anchorDate || todayIn(store.info.timezone);
  mount.replaceChildren(spinner());
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
      mount.replaceChildren(h('p', { class: 'small muted' }, friendly(e)));
    }
  }

  function draw() {
    const grid = h('div', { class: 'schedule-week' });
    for (const day of schedule.days) {
      const enabled = h('input', { class: 'check', type: 'checkbox', checked: day.enabled, 'aria-label': day.label });
      const start = timeInput({ value: day.enabled ? toTimeInput(day.start_time) : '09:00', required: true });
      const end = timeInput({ value: day.enabled ? toTimeInput(day.end_time) : '18:00', required: true });
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
          const on = row.querySelector('.check').checked;
          const inputs = row.querySelectorAll('input[data-time24]');
          return {
            weekday: wd,
            enabled: on,
            start_time: fromTimeInput(readTimeInput(inputs[0])),
            end_time: fromTimeInput(readTimeInput(inputs[1])),
          };
        });
        try {
          await api.put(`/manager/staff/${staffId}/schedule`, { days });
          toast('График сохранён');
          opts.onSaved?.();
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

    const quickDate = h('p', { class: 'small muted' }, `Быстрые действия на ${anchorDate}:`);
    const quickRow = h(
      'div',
      { class: 'row wrap', style: { gap: '8px', marginBottom: '12px' } },
      h(
        'button',
        {
          class: 'btn sm',
          type: 'button',
          onclick: () => postDayOff(anchorDate),
        },
        'Выходной в этот день',
      ),
      h(
        'button',
        {
          class: 'btn sm',
          type: 'button',
          onclick: () => openOverride(anchorDate),
        },
        'Особые часы в этот день',
      ),
    );

    mount.replaceChildren(
      h('h3', null, 'Недельный шаблон'),
      grid,
      save,
      h('h3', { style: { marginTop: '20px' } }, 'Исключения по датам'),
      quickDate,
      quickRow,
      excList.children.length ? excList : h('p', { class: 'muted small' }, 'Нет исключений на ближайшие 90 дней.'),
      h(
        'div',
        { class: 'row wrap', style: { gap: '8px', marginTop: '12px' } },
        h('button', { class: 'btn sm', type: 'button', onclick: () => openDayOff() }, 'Выходной на дату…'),
        h('button', { class: 'btn sm', type: 'button', onclick: () => openOverride() }, 'Особые часы…'),
      ),
    );
  }

  async function removeExc(id) {
    if (!(await confirmDialog('Удалить исключение?'))) return;
    try {
      await api.delete(`/manager/staff/${staffId}/exceptions/${id}`);
      toast('Удалено');
      await reload();
      opts.onSaved?.();
    } catch (e) {
      toast(friendly(e), true);
    }
  }

  async function postDayOff(day) {
    try {
      await api.post(`/manager/staff/${staffId}/exceptions/day-off`, { date: day, note: null });
      toast('Выходной добавлен');
      await reload();
      opts.onSaved?.();
    } catch (e) {
      toast(friendly(e), true);
    }
  }

  function openDayOff(prefill) {
    const date = h('input', { class: 'input', type: 'date', value: prefill || from });
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
              opts.onSaved?.();
            } catch (e) {
              toast(friendly(e), true);
            }
          }),
        );
        sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), ok);
      },
    });
  }

  function openOverride(prefillDate) {
    const date = h('input', { class: 'input', type: 'date', value: prefillDate || from });
    const start = timeInput({ value: '10:00', required: true });
    const end = timeInput({ value: '16:00', required: true });
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
                start_time: fromTimeInput(readTimeInput(start)),
                end_time: fromTimeInput(readTimeInput(end)),
              });
              sheet.close();
              toast('Исключение сохранено');
              await reload();
              opts.onSaved?.();
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
}

export function openScheduleEditor(staffId, opts = {}) {
  openSheet({
    title: 'График мастера',
    build: (sheet) => {
      const host = h('div', { class: 'col' });
      sheet.body.append(host);
      mountScheduleEditor(host, staffId, { ...opts, onSaved: () => { opts.onSaved?.(); } });
    },
  });
}

/** @param {{ id: string, name: string }[]} staffList */
export function openScheduleRulesPicker(staffList, { anchorDate, onSaved } = {}) {
  openSheet({
    title: 'Смены и правила',
    build: (sheet) => {
      const list = h('div', { class: 'list' });
      for (const s of staffList) {
        list.append(
          h(
            'button',
            {
              class: 'card row between',
              type: 'button',
              style: { width: '100%', textAlign: 'left' },
              onclick: () => {
                sheet.close();
                openScheduleEditor(s.id, { anchorDate, onSaved });
              },
            },
            h('b', null, s.name),
            icon('chevR'),
          ),
        );
      }
      sheet.body.append(h('p', { class: 'small muted' }, 'Недельный шаблон и исключения для выбранного мастера.'), list);
      sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'));
    },
  });
}