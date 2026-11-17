import { api, friendly } from '../api.js';
import {
  addDays, dayLabel, dayNumber, duration, fromMin, h, icon, longDayLabel, money, nowMinutesIn, plural,
  signedMoney, todayIn, toMin, weekdayShort,
} from '../util.js';
import { store } from '../store.js';
import { avatar, confirmDialog, emptyState, field, openSheet, spinner, toast, withBusy } from '../ui.js';

const STRIP_DAYS = 28;
const CELL_H = 84;
const LANE_GAP = 10;
const ADD_W = 84;

const STATUS_LABEL = { free: 'Свободна', partial: 'Частично занята', full: 'Занята' };
const BOOKING_STATUS = { booked: 'Записан', confirmed: 'Подтверждён', held: 'Удержание', arrived: 'Пришёл' };

export function dayView({ manager }) {
  const tz = store.info.timezone;
  const today = todayIn(tz);
  let date = sessionStorage.getItem('beaty.day') || today;
  let stripStart = addDays(date, -2);
  let scope = 'own';
  let counts = {};
  let data = null;
  let loadSeq = 0;
  let catalog = null;

  const root = h('div');
  const head = h('div', { class: 'page-head' });
  const strip = h('div', { class: 'date-strip', role: 'tablist', 'aria-label': 'Дни' });
  const statsEl = h('div', { class: 'stats' });
  const barCard = h('div', { class: 'card timeline-wrap' });
  root.append(head, strip, statsEl, barCard);

  const prefix = manager ? '/manager' : '/specialist';

  async function loadCatalog() {
    if (!catalog) catalog = await api.get('/client/catalog');
    return catalog;
  }

  function renderHead() {
    const picker = h('input', { class: 'input', type: 'date', value: date, 'aria-label': 'Выбрать дату', style: { width: 'auto', minHeight: '40px', flex: '1 1 140px' } });
    picker.addEventListener('change', () => picker.value && setDate(picker.value));
    const nav = h(
      'div',
      { class: 'row wrap' },
      h('button', { class: 'btn icon-btn', type: 'button', 'aria-label': 'Предыдущий день', onclick: () => setDate(addDays(date, -1)) }, icon('chevL')),
      h('button', { class: 'btn sm', type: 'button', onclick: () => setDate(today) }, 'Сегодня'),
      h('button', { class: 'btn icon-btn', type: 'button', 'aria-label': 'Следующий день', onclick: () => setDate(addDays(date, 1)) }, icon('chevR')),
      picker,
    );
    const title = h(
      'div',
      null,
      h('h1', null, manager ? 'Расписание' : 'Мой день'),
      h('p', null, `${longDayLabel(date)}${date === today ? ' · сегодня' : ''}`),
    );
    head.replaceChildren(title, nav);
    if (!manager) {
      head.append(
        h(
          'div',
          { class: 'chips', style: { width: '100%' } },
          h('button', { class: `chip ${scope === 'own' ? 'active' : ''}`, type: 'button', onclick: () => setScope('own') }, 'Моё расписание'),
          h('button', { class: `chip ${scope === 'all' ? 'active' : ''}`, type: 'button', onclick: () => setScope('all') }, 'Весь салон'),
          h('span', { class: 'chip' }, 'Только просмотр'),
        ),
      );
    }
  }

  function renderStrip() {
    strip.replaceChildren();
    let activeEl = null;
    for (let i = 0; i < STRIP_DAYS; i += 1) {
      const d = addDays(stripStart, i);
      const pill = h(
        'button',
        {
          class: `day-pill ${d === date ? 'active' : ''} ${counts[d] ? 'has' : ''} ${d === today ? 'today' : ''}`,
          type: 'button',
          role: 'tab',
          'aria-selected': d === date,
          'aria-label': `${dayLabel(d)}${counts[d] ? `, ячеек: ${counts[d]}` : ''}`,
          onclick: () => setDate(d),
        },
        h('div', { class: 'wd' }, weekdayShort(d)),
        h('div', { class: 'dn' }, dayNumber(d)),
        h('i', { class: 'dot' }),
      );
      if (d === date) activeEl = pill;
      strip.append(pill);
    }
    if (activeEl) requestAnimationFrame(() => activeEl.scrollIntoView({ inline: 'center', block: 'nearest' }));
  }

  function renderStats() {
    const s = data.stats;
    statsEl.replaceChildren(
      statBox(s.shifts != null ? s.shifts : s.cells, plural(s.shifts != null ? s.shifts : s.cells, 'смена', 'смены', 'смен')),
      statBox(s.bookings, plural(s.bookings, 'запись', 'записи', 'записей')),
      statBox(duration(s.free_minutes), 'свободно'),
    );
  }

  const statBox = (value, label) => h('div', { class: 'card stat' }, h('b', null, value), h('span', null, label));

  function layoutLanes(cells) {
    const laneEnds = [];
    const placed = [];
    const sorted = [...cells].sort((a, b) => toMin(a.start) - toMin(b.start) || toMin(a.end === '24:00' ? '23:59' : a.end) - toMin(b.end === '24:00' ? '23:59' : b.end));
    for (const cell of sorted) {
      const s = toMin(cell.start);
      const e = cell.end === '24:00' ? 1440 : toMin(cell.end);
      let lane = laneEnds.findIndex((end) => end <= s);
      if (lane === -1) {
        lane = laneEnds.length;
        laneEnds.push(0);
      }
      laneEnds[lane] = e;
      placed.push({ cell, lane, s, e });
    }
    return { placed, lanes: Math.max(laneEnds.length, 1) };
  }

  function renderBar() {
    const pxh = window.innerWidth < 820 ? 88 : 124;
    const pxm = pxh / 60;
    const cells = data.cells;
    let startMin = Math.floor(toMin(data.work_start) / 60) * 60;
    let endMin = Math.ceil(toMin(data.work_end) / 60) * 60;
    for (const c of cells) {
      startMin = Math.min(startMin, Math.floor(toMin(c.start) / 60) * 60);
      endMin = Math.max(endMin, Math.ceil((c.end === '24:00' ? 1440 : toMin(c.end)) / 60) * 60);
    }
    const { placed, lanes } = layoutLanes(cells);
    const lastEnd = placed.reduce((m, p) => Math.max(m, p.e), 0);
    const addLeft = (Math.max(lastEnd, startMin) - startMin) * pxm + 10;
    const baseWidth = (endMin - startMin) * pxm;
    const width = Math.max(baseWidth, manager ? addLeft + ADD_W + 16 : baseWidth);
    const lanesHeight = lanes * (CELL_H + LANE_GAP) - LANE_GAP;

    const timeline = h('div', { class: 'timeline', style: { width: `${width + 32}px`, paddingLeft: '16px', paddingRight: '16px' } });
    const ticks = h('div', { class: 'ticks' });
    const lanesEl = h('div', { class: 'lanes', style: { height: `${lanesHeight}px` } });
    for (let m = startMin; m <= endMin; m += 60) {
      const x = (m - startMin) * pxm;
      ticks.append(h('span', { class: `tick ${m === startMin ? 'first' : ''}`, style: { left: `${x}px` } }, fromMin(m % 1440 === 0 && m > 0 ? 0 : m)));
      lanesEl.append(h('i', { class: 'gridline', style: { left: `${x}px` } }));
    }
    if (date === today) {
      const nowMin = nowMinutesIn(tz);
      if (nowMin >= startMin && nowMin <= endMin) lanesEl.append(h('i', { class: 'now-line', style: { left: `${(nowMin - startMin) * pxm}px` }, title: 'Сейчас' }));
    }

    for (const { cell, lane, s, e } of placed) {
      const w = (e - s) * pxm - 4;
      const left = (s - startMin) * pxm;
      const booked = cell.minutes ? Math.round(((cell.minutes - cell.free_minutes) / cell.minutes) * 100) : 0;
      const label = `${cell.start}–${cell.end}, ${cell.staff.name}, ${STATUS_LABEL[cell.status]}`;
      const timeText = w >= 150 ? `${cell.start}–${cell.end}` : w >= 90 ? cell.start : '';
      const el = h(
        'button',
        {
          class: `cell s-${cell.status} ${w < 70 ? 'compact' : ''} ${w < 130 ? 'tiny-time' : ''}`,
          type: 'button',
          style: { left: `${left}px`, top: `${lane * (CELL_H + LANE_GAP)}px`, width: `${w}px` },
          title: label,
          'aria-label': label,
          onclick: () => openCellModal(cell),
        },
        h('div', { class: 'c-time' }, timeText),
        h('div', { class: 'c-who' }, avatar(cell.staff, 'sm'), h('span', null, cell.staff.name)),
        h('div', { class: 'c-fill' }, h('i', { style: { width: `${booked}%` } })),
      );
      lanesEl.append(el);
    }

    const legacyCells = cells.some((c) => !c.schedule_window);
    if (manager && legacyCells) {
      const add = h(
        'button',
        {
          class: `cell-add ${cells.length ? '' : 'wide'}`,
          type: 'button',
          style: cells.length ? { left: `${addLeft}px`, top: '0px' } : { top: '0px' },
          'aria-label': 'Добавить ячейку',
          title: 'Добавить ячейку',
          onclick: () => openCellForm(null, { suggestStart: Math.max(lastEnd, toMin(data.work_start)) }),
        },
        cells.length ? icon('plus') : h('span', { class: 'row', style: { justifyContent: 'center', gap: '8px', fontWeight: 700 } }, icon('plus'), 'Добавить первую ячейку'),
      );
      lanesEl.append(add);
    }

    timeline.append(ticks, lanesEl);
    const scroller = h('div', { class: 'timeline-scroll' }, timeline);
    const legend = h(
      'div',
      { class: 'legend' },
      ['free', 'partial', 'full'].map((k) =>
        h('span', null, h('i', { style: { background: k === 'free' ? 'var(--ok)' : k === 'partial' ? 'var(--warn)' : 'var(--bad)' } }), STATUS_LABEL[k]),
      ),
    );
    barCard.replaceChildren(scroller, legend);
    requestAnimationFrame(() => {
      const target = date === today ? (nowMinutesIn(tz) - startMin) * pxm - 80 : placed.length ? (placed[0].s - startMin) * pxm - 20 : 0;
      scroller.scrollLeft = Math.max(0, target);
    });
    if (!cells.length && !manager) {
      barCard.replaceChildren(emptyState('🗓️', 'В этот день смены нет', scope === 'own' ? 'По графику вы не работаете в этот день.' : 'Никто из мастеров не работает в этот день.'));
    }
  }

  async function load() {
    const seq = ++loadSeq;
    barCard.replaceChildren(spinner());
    try {
      const dayPath = `${prefix}/day?date=${date}${manager ? '' : `&scope=${scope}`}`;
      const countsPath = `${prefix}/cells/counts?${manager ? '' : `scope=${scope}&`}from=${stripStart}&days=${STRIP_DAYS}`;
      const [day, cnt] = await Promise.all([api.get(dayPath), api.get(countsPath)]);
      if (seq !== loadSeq) return;
      data = day;
      counts = cnt;
      renderHead();
      renderStrip();
      renderStats();
      renderBar();
    } catch (e) {
      if (seq !== loadSeq) return;
      if (e.status === 401) throw e;
      barCard.replaceChildren(emptyState('⚠️', 'Не удалось загрузить', friendly(e)));
    }
  }

  function setDate(d) {
    date = d;
    sessionStorage.setItem('beaty.day', d);
    const idx = Math.round((new Date(`${d}T12:00:00Z`) - new Date(`${stripStart}T12:00:00Z`)) / 86400000);
    if (idx < 0 || idx >= STRIP_DAYS - 3) stripStart = addDays(d, -2);
    load();
  }

  function setScope(s) {
    scope = s;
    load();
  }

  async function openCellModal(cell) {
    const cat = await loadCatalog().catch(() => ({ services: [] }));
    const nameById = new Map(cat.services.map((s) => [s.id, s.name]));
    openSheet({
      title: cell.schedule_window ? 'Смена' : 'Ячейка',
      build: (sheet) => {
        const s = cell.staff;
        const booked = cell.minutes - cell.free_minutes;
        sheet.body.append(
          h(
            'div',
            { class: 'hero' },
            avatar(s, 'xl'),
            h('h2', null, s.name),
            s.specialization ? h('span', { class: 'chip active' }, s.specialization) : null,
            s.bio ? h('p', { class: 'muted small' }, s.bio) : null,
          ),
          h(
            'dl',
            { class: 'kv' },
            h('dt', null, 'Дата'), h('dd', null, dayLabel(cell.date)),
            h('dt', null, 'Время'), h('dd', { class: 'num' }, `${cell.start}–${cell.end}`),
            h('dt', null, 'Длительность'), h('dd', null, duration(cell.minutes)),
            h('dt', null, 'Свободно'), h('dd', null, `${duration(cell.free_minutes)} из ${duration(cell.minutes)}`),
            cell.price_cents ? [h('dt', null, 'Корректировка цены'), h('dd', null, signedMoney(cell.price_cents))] : null,
            h('dt', null, 'Статус'), h('dd', null, h('span', { class: `chip ${cell.status === 'free' ? 'ok' : cell.status === 'partial' ? 'warn' : 'bad'}` }, STATUS_LABEL[cell.status])),
          ),
          h('div', { class: 'meter', 'aria-hidden': 'true' }, h('i', { style: { width: `${cell.minutes ? (booked / cell.minutes) * 100 : 0}%` } })),
          cell.title ? h('h3', null, cell.title) : null,
          cell.description ? h('p', null, cell.description) : null,
          cell.allowed_service_ids.length
            ? h('div', { class: 'col' }, h('span', { class: 'label' }, 'Доступные услуги'), h('div', { class: 'chips' }, cell.allowed_service_ids.map((id) => h('span', { class: 'chip' }, nameById.get(id) || 'Услуга'))))
            : h('p', { class: 'small muted' }, 'Доступны все услуги специалиста.'),
          h('div', { class: 'col' }, h('span', { class: 'label' }, `Записи (${cell.bookings.length})`), bookingList(cell)),
        );
        if (manager && !cell.schedule_window) {
          sheet.setFooter(
            h('button', { class: 'btn danger', type: 'button', onclick: () => removeCell(cell, sheet) }, icon('trash'), 'Удалить'),
            h('button', { class: 'btn primary', type: 'button', onclick: () => { sheet.close(); openCellForm(cell); } }, icon('edit'), 'Изменить'),
          );
        } else {
          sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'));
        }
      },
    });
  }

  function bookingList(cell) {
    if (!cell.bookings.length) return h('p', { class: 'small muted' }, 'Пока никто не записался.');
    return h(
      'div',
      { class: 'col' },
      cell.bookings.map((b) =>
        h(
          'div',
          { class: 'bk' },
          h('div', { class: 'row between' }, h('b', { class: 'num' }, `${b.start}–${b.end}`), h('span', { class: 'chip ok' }, BOOKING_STATUS[b.status] || b.status)),
          b.client_name ? h('div', null, b.client_name) : h('div', { class: 'muted small' }, 'Клиент скрыт'),
          h('div', { class: 'small muted' }, b.service_names.join(', ')),
          b.client_phone ? h('a', { class: 'small', href: `tel:+${b.client_phone}` }, `+${b.client_phone}`) : null,
          b.comment ? h('div', { class: 'small' }, `«${b.comment}»`) : null,
          h('div', { class: 'small muted' }, money(b.total_price_cents)),
        ),
      ),
    );
  }

  async function removeCell(cell, sheet) {
    const ok = await confirmDialog({ title: 'Удалить ячейку?', text: `${cell.start}–${cell.end}, ${cell.staff.name}. Действие нельзя отменить.`, confirmLabel: 'Удалить', danger: true });
    if (!ok) return;
    try {
      await api.del(`/manager/cells/${cell.id}`);
      sheet.close();
      toast('Ячейка удалена');
      load();
    } catch (e) {
      toast(friendly(e), true);
    }
  }

  async function openCellForm(cell, opts = {}) {
    let staff;
    let services;
    try {
      [staff, services] = await Promise.all([api.get('/manager/staff'), api.get('/manager/services')]);
    } catch (e) {
      toast(friendly(e), true);
      return;
    }
    staff = staff.filter((s) => s.is_active);
    services = services.filter((s) => s.is_active);
    if (!staff.length) {
      toast('Сначала добавьте специалиста', true);
      location.hash = '#/team';
      return;
    }
    const editing = Boolean(cell);
    const suggest = opts.suggestStart ?? toMin(data.work_start);
    const startDefault = Math.min(suggest, 23 * 60);
    const state = {
      staffId: editing ? cell.staff.id : staff[0].id,
      start: editing ? cell.start : fromMin(startDefault),
      end: editing ? cell.end : fromMin(Math.min(startDefault + 60, 24 * 60 - 5)),
      allowed: new Set(editing ? cell.allowed_service_ids : []),
    };
    const lockedStaff = editing && cell.bookings.length > 0;

    openSheet({
      title: editing ? 'Изменить ячейку' : 'Новая ячейка',
      build: (sheet) => {
        const startInput = h('input', { class: 'input', type: 'time', step: '300', value: state.start, required: true });
        const endInput = h('input', { class: 'input', type: 'time', step: '300', value: state.end === '24:00' ? '23:59' : state.end, required: true });
        const priceInput = h('input', { class: 'input', type: 'number', step: '50', inputmode: 'decimal', placeholder: '0', value: editing && cell.price_cents ? cell.price_cents / 100 : '' });
        const titleInput = h('input', { class: 'input', type: 'text', maxlength: '255', placeholder: 'Например, «Вечернее окно»', value: editing ? cell.title || '' : '' });
        const descInput = h('textarea', { class: 'textarea', maxlength: '2000', placeholder: 'Что важно знать клиенту' }, editing ? cell.description || '' : '');
        const durLabel = h('span', { class: 'small muted' });
        const error = h('p', { class: 'small', style: { color: 'var(--bad)' }, role: 'alert' });

        const updateDur = () => {
          const d = toMin(endInput.value || '00:00') - toMin(startInput.value || '00:00');
          durLabel.textContent = d > 0 ? `Длительность: ${duration(d)}` : 'Конец должен быть позже начала';
        };
        let lastDur = Math.max(5, toMin(endInput.value) - toMin(startInput.value));
        startInput.addEventListener('change', () => {
          const e = Math.min(toMin(startInput.value) + lastDur, 24 * 60 - 1);
          endInput.value = fromMin(e);
          updateDur();
        });
        endInput.addEventListener('change', () => {
          const d = toMin(endInput.value) - toMin(startInput.value);
          if (d > 0) lastDur = d;
          updateDur();
        });
        updateDur();

        const quick = h(
          'div',
          { class: 'chips' },
          [30, 60, 90, 120, 180, 240].map((m) =>
            h('button', { class: 'chip', type: 'button', onclick: () => {
              endInput.value = fromMin(Math.min(toMin(startInput.value) + m, 24 * 60 - 1));
              lastDur = m;
              updateDur();
            } }, duration(m)),
          ),
        );

        const picker = h('div', { class: 'picker' });
        const drawPicker = () => {
          picker.replaceChildren(
            ...staff.map((s) =>
              h('button', { class: `pick ${s.id === state.staffId ? 'on' : ''}`, type: 'button', disabled: lockedStaff && s.id !== state.staffId, onclick: () => { state.staffId = s.id; drawPicker(); } }, avatar(s), h('span', null, s.name)),
            ),
          );
        };
        drawPicker();

        const svcChips = h('div', { class: 'chips' });
        const drawSvc = () => {
          svcChips.replaceChildren(
            ...services.map((s) =>
              h('button', { class: `chip ${state.allowed.has(s.id) ? 'active' : ''}`, type: 'button', onclick: () => { state.allowed.has(s.id) ? state.allowed.delete(s.id) : state.allowed.add(s.id); drawSvc(); } }, s.name),
            ),
          );
        };
        drawSvc();

        sheet.body.append(
          field('Специалист', picker, lockedStaff ? 'В ячейке есть записи: специалиста сменить нельзя.' : undefined),
          h('div', { class: 'grid2' }, field('Начало', startInput), field('Конец', endInput)),
          h('div', { class: 'col', style: { gap: '6px' } }, quick, durLabel),
          field('Корректировка цены, ₽', priceInput, 'Необязательно. Прибавляется к стоимости услуг (можно отрицательное значение для скидки).'),
          field('Название', titleInput),
          field('Описание', descInput),
          field('Допустимые услуги', svcChips, 'Не выбрано — подойдут все услуги специалиста.'),
          error,
        );

        const save = h('button', { class: 'btn primary', type: 'button' }, editing ? 'Сохранить' : 'Создать ячейку');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            error.textContent = '';
            const body = {
              staff_member_id: state.staffId,
              date: editing ? cell.date : date,
              start: startInput.value,
              end: endInput.value,
              price_cents: priceInput.value === '' ? null : Math.round(Number(priceInput.value) * 100),
              title: titleInput.value.trim() || null,
              description: descInput.value.trim() || null,
              allowed_service_ids: [...state.allowed],
            };
            if (!body.start || !body.end || toMin(body.end) <= toMin(body.start)) {
              error.textContent = 'Конец должен быть позже начала.';
              return;
            }
            try {
              if (editing) await api.patch(`/manager/cells/${cell.id}`, body);
              else await api.post('/manager/cells', body);
              sheet.close();
              toast(editing ? 'Ячейка обновлена' : 'Ячейка добавлена');
              load();
            } catch (e) {
              error.textContent = friendly(e);
            }
          }),
        );
        sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), save);
      },
    });
  }

  load();
  const onResize = () => data && renderBar();
  window.addEventListener('resize', onResize);
  root.cleanup = () => window.removeEventListener('resize', onResize);
  return root;
}
