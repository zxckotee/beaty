import { api, friendly } from '../api.js';
import { TIME_INPUT_CLASS, h, icon, readTimeInput, timeInput } from '../util.js';
import { avatar, confirmDialog, emptyState, field, openSheet, spinner, toast, withBusy } from '../ui.js';
import { navigate } from '../main.js';

function collectDaysFromGrid(grid) {
  return [...grid.querySelectorAll('.schedule-day')].map((row) => {
    const wd = Number(row.dataset.wd);
    const on = row.querySelector('.check').checked;
    const inputs = row.querySelectorAll(`input.${TIME_INPUT_CLASS}`);
    if (!on) return { weekday: wd, enabled: false };
    return {
      weekday: wd,
      enabled: true,
      start_time: readTimeInput(inputs[0]),
      end_time: readTimeInput(inputs[1]),
    };
  });
}

function buildWeeklyGrid(initialDays, weekdayLabels) {
  const grid = h('div', { class: 'schedule-week' });
  const byWd = Object.fromEntries((initialDays || []).map((d) => [d.weekday, d]));
  for (let wd = 0; wd < 7; wd += 1) {
    const day = byWd[wd] || { weekday: wd, enabled: wd < 5, start_time: '09:00', end_time: '18:00' };
    const enabled = h('input', { class: 'check', type: 'checkbox', checked: day.enabled, 'aria-label': weekdayLabels[wd] });
    const start = timeInput({ value: day.start_time || '09:00' });
    const end = timeInput({ value: day.end_time === '24:00' ? '23:59' : day.end_time || '18:00' });
    const toggle = () => { start.disabled = end.disabled = !enabled.checked; };
    enabled.addEventListener('change', toggle);
    toggle();
    grid.append(
      h(
        'div',
        { class: 'card schedule-day', 'data-wd': String(wd) },
        h('label', { class: 'row between' }, h('b', null, weekdayLabels[wd] || day.label), enabled),
        h('div', { class: 'grid2' }, field('С', start), field('До', end)),
      ),
    );
  }
  return grid;
}

function openRuleForm(rule, weekdayLabels, onSaved) {
  const name = h('input', { class: 'input', type: 'text', maxlength: '120', required: true, value: rule?.name || '', placeholder: 'Например, «Стандартная неделя»' });
  const grid = buildWeeklyGrid(rule?.days, weekdayLabels);
  openSheet({
    title: rule ? 'Изменить шаблон' : 'Новый шаблон недели',
    build: (sheet) => {
      sheet.body.append(
        field('Название шаблона', name),
        h('p', { class: 'small muted' }, 'Каждый день недели — пункт правила. Часы работы в этот день — значение пункта.'),
        grid,
      );
      const save = h('button', { class: 'btn primary', type: 'button' }, rule ? 'Сохранить' : 'Создать');
      save.addEventListener('click', () =>
        withBusy(save, async () => {
          const body = { name: name.value.trim(), days: collectDaysFromGrid(grid) };
          if (!body.name) {
            toast('Укажите название', true);
            return;
          }
          try {
            if (rule) await api.patch(`/manager/schedule-rules/${rule.id}`, body);
            else await api.post('/manager/schedule-rules', body);
            sheet.close();
            toast(rule ? 'Шаблон обновлён' : 'Шаблон создан');
            onSaved();
          } catch (e) {
            toast(friendly(e), true);
          }
        }),
      );
      sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), save);
    },
  });
}

function openApplyForm(rule, staffList, onDone) {
  openSheet({
    title: `Назначить: ${rule.name}`,
    build: (sheet) => {
      const staffWrap = h('div', { class: 'col' });
      const picked = new Set(staffList.map((s) => s.id));
      for (const s of staffList) {
        const on = h('input', { class: 'check', type: 'checkbox', checked: true });
        on.addEventListener('change', () => {
          if (on.checked) picked.add(s.id);
          else picked.delete(s.id);
        });
        staffWrap.append(h('label', { class: 'row' }, on, avatar(s, 'sm'), h('span', null, s.name)));
      }
      sheet.body.append(
        h('p', { class: 'small muted' }, rule.summary),
        h('p', { class: 'small muted' }, 'Индивидуальное правило мастера важнее правила салона по умолчанию.'),
        field(
          'По умолчанию для всего салона',
          h('p', { class: 'small' }, 'Для мастеров без своего шаблона. У кого уже выбран другой шаблон — не меняется.'),
        ),
        h(
          'button',
          {
            class: 'btn primary block',
            type: 'button',
            id: 'apply-default-btn',
          },
          'Сделать правилом салона по умолчанию',
        ),
        h('hr', { style: { border: 'none', borderTop: '1px solid var(--line)', margin: '16px 0' } }),
        field('Или назначить индивидуально мастерам', staffWrap),
      );
      const applyStaff = h('button', { class: 'btn soft block', type: 'button' }, 'Назначить выбранным мастерам');
      applyStaff.addEventListener('click', () =>
        withBusy(applyStaff, async () => {
          if (!picked.size) {
            toast('Выберите мастеров', true);
            return;
          }
          try {
            const res = await api.post(`/manager/schedule-rules/${rule.id}/apply`, {
              scope: 'staff',
              staff_member_ids: [...picked],
            });
            sheet.close();
            toast(`Индивидуально: ${res.staff_updated} мастеров`);
            onDone();
          } catch (e) {
            toast(friendly(e), true);
          }
        }),
      );
      sheet.setFooter(
        h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'),
        applyStaff,
      );
      sheet.body.querySelector('#apply-default-btn').addEventListener('click', (ev) =>
        withBusy(ev.target, async () => {
          try {
            const res = await api.post(`/manager/schedule-rules/${rule.id}/apply`, { scope: 'enterprise_default' });
            sheet.close();
            toast(`Правило салона: обновлено ${res.staff_updated} мастеров без индивидуального шаблона`);
            onDone();
          } catch (e) {
            toast(friendly(e), true);
          }
        }),
      );
    },
  });
}

export async function scheduleRulesView({ embedded = false } = {}) {
  const root = h('div', { class: 'col schedule-rules-embed' });
  let weekdayLabels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
  const openNew = () => openRuleForm(null, weekdayLabels, load);
  const titleTag = embedded ? 'h3' : 'h1';
  const head = h(
    'div',
    { class: embedded ? 'row between schedule-rules-embed-head' : 'row between', style: { flexWrap: 'wrap', gap: '12px' } },
    h('div', null,
      h(titleTag, null, 'Шаблоны расписания'),
      h('p', { class: 'muted small' }, 'Недельное правило: каждый день — свой пункт с часами. Назначайте мастерам или всему салону.'),
    ),
    h('button', { class: 'btn sm primary', type: 'button', onclick: openNew }, icon('plus'), 'Добавить'),
  );
  if (!embedded) {
    head.insertBefore(
      h('button', { class: 'btn sm', type: 'button', onclick: () => navigate('dashboard') }, icon('chevL'), 'К дашборду'),
      head.lastChild,
    );
  }
  root.append(head);
  const list = h('div', { class: 'list' });
  root.append(list);
  list.append(spinner());

  async function load() {
    list.replaceChildren(spinner());
    try {
      const [rulesRes, staffRes] = await Promise.all([api.get('/manager/schedule-rules'), api.get('/manager/staff')]);
      const items = rulesRes.items || [];
      const staff = (staffRes || []).filter((s) => s.is_active);
      weekdayLabels = rulesRes.weekday_labels || weekdayLabels;
      const defaultId = rulesRes.default_schedule_rule_id;
      list.replaceChildren();
      if (defaultId) {
        const def = items.find((r) => r.id === defaultId);
        list.append(
          h('div', { class: 'card soft' },
            h('p', { class: 'small' }, 'Правило салона по умолчанию: ', h('b', null, def ? def.name : '—')),
          ),
        );
      }
      if (!items.length) {
        list.append(
          emptyState(
            '📋',
            'Создайте первый шаблон',
            'Опишите всю неделю, затем назначьте салону или мастерам.',
            h('button', { class: 'btn primary', type: 'button', onclick: openNew }, icon('plus'), 'Создать шаблон'),
          ),
        );
        return;
      }
      for (const rule of items) {
        list.append(
          h('div', { class: 'card col', style: { gap: '10px' } },
            h('div', { class: 'row between' },
              h('div', null,
                rule.is_default ? h('span', { class: 'chip active tiny' }, 'Салон') : null,
                h('b', null, rule.name),
                h('div', { class: 'small muted' }, rule.summary),
              ),
              h('div', { class: 'row', style: { gap: '6px' } },
                h('button', { class: 'btn sm', type: 'button', onclick: () => openApplyForm(rule, staff, load) }, 'Назначить'),
                h('button', { class: 'btn sm ghost', type: 'button', onclick: () => openRuleForm(rule, weekdayLabels, load) }, icon('edit')),
                h('button', { class: 'btn sm ghost', type: 'button', onclick: async () => {
                  if (!(await confirmDialog({ title: 'Удалить шаблон?', text: rule.name, confirmLabel: 'Удалить', danger: true }))) return;
                  try {
                    await api.delete(`/manager/schedule-rules/${rule.id}`);
                    toast('Удалено');
                    load();
                  } catch (e) {
                    toast(friendly(e), true);
                  }
                } }, icon('trash')),
              ),
            ),
          ),
        );
      }
      list.append(h('button', { class: 'btn block soft', type: 'button', onclick: openNew }, icon('plus'), 'Добавить шаблон'));
    } catch (e) {
      list.replaceChildren(h('p', { class: 'small muted' }, friendly(e)));
    }
  }

  await load();
  return root;
}