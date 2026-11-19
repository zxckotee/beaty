import { api, friendly } from './api.js';
import { h, icon, todayIn } from './util.js';
import { store } from './store.js';
import { navigate } from './main.js';
import { confirmDialog, field, openSheet, spinner, toast, withBusy } from './ui.js';

function toTimeInput(hhmm) {
  if (hhmm === '24:00') return '23:59';
  return hhmm.length === 5 ? `${hhmm}:00`.slice(0, 5) : hhmm;
}

function fromTimeInput(value) {
  if (!value) return '09:00';
  const [hh, mm] = value.split(':');
  return `${hh.padStart(2, '0')}:${mm.padStart(2, '0')}`;
}

function ruleHoursLabel(rule) {
  if (!rule) return '';
  return `${rule.start_time}–${rule.end_time}`;
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
      const sched = await api.get(`/manager/staff/${staffId}/schedule`);
      schedule = sched;
      exceptions = await api.get(`/manager/staff/${staffId}/exceptions?from=${from}&days=90`);
      draw();
    } catch (e) {
      mount.replaceChildren(h('p', { class: 'small muted' }, friendly(e)));
    }
  }

  function draw() {
    const rules = schedule.rules || [];
    const grid = h('div', { class: 'schedule-week' });
    for (const day of schedule.days) {
      const enabled = h('input', { class: 'check', type: 'checkbox', checked: day.enabled, 'aria-label': day.label });
      const ruleSelect = h('select', { class: 'input select' });
      ruleSelect.append(h('option', { value: '' }, '— нет смены —'));
      for (const r of rules) {
        ruleSelect.append(h('option', { value: r.id }, r.label || `${r.name} (${r.start_time}–${r.end_time})`));
      }
      if (day.rule_id) ruleSelect.value = day.rule_id;
      const hint = h('span', { class: 'tiny muted num' });
      const syncHint = () => {
        const r = rules.find((x) => x.id === ruleSelect.value);
        hint.textContent = ruleSelect.value ? ruleHoursLabel(r) : '';
      };
      ruleSelect.addEventListener('change', syncHint);
      syncHint();
      const toggle = () => {
        ruleSelect.disabled = !enabled.checked;
      };
      enabled.addEventListener('change', toggle);
      toggle();
      grid.append(
        h(
          'div',
          { class: 'card schedule-day', 'data-wd': String(day.weekday) },
          h('label', { class: 'row between' }, h('b', null, day.label), enabled),
          field('Правило смены', ruleSelect, hint),
        ),
      );
    }

    const rulesLink = h('button', {
      class: 'btn sm soft',
      type: 'button',
      onclick: () => { if (opts.closeSheet) opts.closeSheet(); navigate('schedule-rules'); },
    }, 'Библиотека правил');

    const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить неделю');
    save.addEventListener('click', () =>
      withBusy(save, async () => {
        const days = [...grid.querySelectorAll('.schedule-day')].map((row) => {
          const wd = Number(row.dataset.wd);
          const on = row.querySelector('.check').checked;
          const sel = row.querySelector('select');
          const ruleId = sel?.value || '';
          if (!on) return { weekday: wd, enabled: false };
          if (!ruleId) return { weekday: wd, enabled: false };
          return { weekday: wd, enabled: true, rule_id: ruleId };
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
      h('p', { class: 'small muted' }, 'Для каждого дня выберите готовое правило. Часы правятся в библиотеке, не у каждого мастера отдельно.'),
      rulesLink,
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
      mountScheduleEditor(host, staffId, {
        ...opts,
        closeSheet: () => sheet.close(),
        onSaved: () => { opts.onSaved?.(); },
      });
    },
  });
}

/** @param {{ id: string, name: string }[]} staffList */
export function openScheduleRulesPicker(staffList, { anchorDate, onSaved } = {}) {
  openSheet({
    title: 'Смены и правила',
    build: (sheet) => {
      const list = h('div', { class: 'list' });
      sheet.body.append(
        h('p', { class: 'small muted' }, 'Сначала создайте или отредактируйте правила смен, затем назначьте их мастерам или всему салону.'),
        h('button', {
          class: 'btn primary block',
          type: 'button',
          onclick: () => { sheet.close(); navigate('schedule-rules'); },
        }, 'Правила смен и назначение'),
        h('p', { class: 'small muted', style: { marginTop: '12px' } }, 'Исключения по датам (выходной, особые часы) — в графике конкретного мастера:'),
        list,
      );
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
      sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'));
    },
  });
}