import { api, friendly } from '../api.js';
import { h, icon } from '../util.js';
import { avatar, confirmDialog, emptyState, field, openSheet, spinner, toast, withBusy } from '../ui.js';
import { navigate } from '../main.js';

const WEEK = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function ruleLabel(r) {
  return r.label || `${r.name} (${r.start_time}–${r.end_time})`;
}

function openRuleForm(rule, onSaved) {
  const name = h('input', { class: 'input', type: 'text', maxlength: '120', required: true, value: rule?.name || '', placeholder: 'Например, «Дневная смена»' });
  const start = h('input', { class: 'input', type: 'time', value: rule?.start_time || '09:00', required: true });
  const end = h('input', { class: 'input', type: 'time', value: rule?.end_time === '24:00' ? '23:59' : rule?.end_time || '18:00', required: true });
  openSheet({
    title: rule ? 'Изменить правило' : 'Новое правило смены',
    build: (sheet) => {
      sheet.body.append(
        field('Название', name, 'Сначала создайте правило, затем назначьте его мастерам.'),
        h('div', { class: 'grid2' }, field('Начало', start), field('Конец', end)),
      );
      const save = h('button', { class: 'btn primary', type: 'button' }, rule ? 'Сохранить' : 'Создать');
      save.addEventListener('click', () =>
        withBusy(save, async () => {
          const body = { name: name.value.trim(), start_time: start.value.slice(0, 5), end_time: end.value.slice(0, 5) };
          if (!body.name) {
            toast('Укажите название', true);
            return;
          }
          try {
            if (rule) await api.patch(`/manager/schedule-rules/${rule.id}`, body);
            else await api.post('/manager/schedule-rules', body);
            sheet.close();
            toast(rule ? 'Правило обновлено' : 'Правило создано');
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
  const dayWrap = h('div', { class: 'chips' });
  const wdOn = new Set([0, 1, 2, 3, 4, 5, 6]);
  for (let i = 0; i < 7; i += 1) {
    const btn = h('button', { class: `chip active`, type: 'button' }, WEEK[i]);
    btn.addEventListener('click', () => {
      if (wdOn.has(i)) {
        wdOn.delete(i);
        btn.classList.remove('active');
      } else {
        wdOn.add(i);
        btn.classList.add('active');
      }
    });
    dayWrap.append(btn);
  }
  const allStaff = h('input', { class: 'check', type: 'checkbox', checked: true, id: 'apply-all-staff' });
  const staffWrap = h('div', { class: 'col' });
  const picked = new Set(staffList.map((s) => s.id));
  function drawStaff() {
    staffWrap.replaceChildren();
    const disabled = allStaff.checked;
    for (const s of staffList) {
      const on = h('input', { class: 'check', type: 'checkbox', checked: picked.has(s.id), disabled });
      on.addEventListener('change', () => {
        if (on.checked) picked.add(s.id);
        else picked.delete(s.id);
      });
      staffWrap.append(h('label', { class: 'row' }, on, avatar(s, 'sm'), h('span', null, s.name)));
    }
  }
  allStaff.addEventListener('change', drawStaff);
  drawStaff();

  openSheet({
    title: `Применить: ${rule.name}`,
    build: (sheet) => {
      sheet.body.append(
        h('p', { class: 'small muted' }, `Часы: ${rule.start_time}–${rule.end_time}. Выбранные дни и мастера получат эту смену в недельном шаблоне.`),
        field('Дни недели', dayWrap),
        field('Все мастера', h('label', { class: 'row' }, allStaff, h('span', null, 'Применить ко всему салону'))),
        field('Или выберите мастеров', staffWrap),
      );
      const ok = h('button', { class: 'btn primary', type: 'button' }, 'Применить');
      ok.addEventListener('click', () =>
        withBusy(ok, async () => {
          if (!wdOn.size) {
            toast('Выберите хотя бы один день', true);
            return;
          }
          if (!allStaff.checked && !picked.size) {
            toast('Выберите мастеров', true);
            return;
          }
          try {
            const res = await api.post(`/manager/schedule-rules/${rule.id}/apply`, {
              weekdays: [...wdOn].sort((a, b) => a - b),
              staff_member_ids: allStaff.checked ? null : [...picked],
            });
            sheet.close();
            toast(`Правило применено (${res.staff_updated} мастеров)`);
            onDone();
          } catch (e) {
            toast(friendly(e), true);
          }
        }),
      );
      sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), ok);
    },
  });
}

export async function scheduleRulesView() {
  const root = h('div', { class: 'col' });
  root.append(
    h('div', { class: 'row between', style: { flexWrap: 'wrap', gap: '12px' } },
      h('div', null, h('h1', null, 'Правила смен'), h('p', { class: 'muted small' }, 'Создайте шаблоны часов и назначайте их мастерам или всему салону.')),
      h('button', { class: 'btn sm', type: 'button', onclick: () => navigate('day') }, icon('chevL'), 'К расписанию'),
    ),
  );
  const list = h('div', { class: 'list' });
  root.append(list);
  list.append(spinner());

  async function load() {
    list.replaceChildren(spinner());
    try {
      const [rulesRes, staffRes] = await Promise.all([api.get('/manager/schedule-rules'), api.get('/manager/staff')]);
      const items = rulesRes.items || [];
      const staff = (staffRes || []).filter((s) => s.is_active);
      list.replaceChildren();
      if (!items.length) {
        list.append(
          emptyState(
            '📋',
            'Пока нет правил',
            'Создайте первое правило смены — например «Дневная 10:00–19:00».',
            h('button', { class: 'btn primary', type: 'button', onclick: () => openRuleForm(null, load) }, icon('plus'), 'Создать правило'),
          ),
        );
        return;
      }
      for (const rule of items) {
        list.append(
          h(
            'div',
            { class: 'card col', style: { gap: '10px' } },
            h('div', { class: 'row between' },
              h('div', null,
                h('b', null, rule.name),
                h('div', { class: 'small muted num' }, `${rule.start_time}–${rule.end_time}`),
              ),
              h('div', { class: 'row', style: { gap: '6px' } },
                h('button', { class: 'btn sm', type: 'button', onclick: () => openApplyForm(rule, staff, load) }, 'Назначить'),
                h('button', { class: 'btn sm ghost', type: 'button', onclick: () => openRuleForm(rule, load) }, icon('edit')),
                h('button', { class: 'btn sm ghost', type: 'button', onclick: async () => {
                  if (!(await confirmDialog({ title: 'Удалить правило?', text: rule.name, confirmLabel: 'Удалить', danger: true }))) return;
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
      list.append(h('button', { class: 'btn block soft', type: 'button', onclick: () => openRuleForm(null, load) }, icon('plus'), 'Добавить правило'));
      if (staff.length) {
        list.append(h('p', { class: 'small muted', style: { marginTop: '8px' } }, 'Назначение по мастеру: в карточке «Применить» выберите дни и «все мастера» или конкретных специалистов. Исключения (выходной, особые часы) по-прежнему в графике мастера.'));
      }
    } catch (e) {
      list.replaceChildren(h('p', { class: 'small muted' }, friendly(e)));
    }
  }

  await load();
  return root;
}