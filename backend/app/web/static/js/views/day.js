import { api, friendly } from '../api.js';
import {
  addDays, dayLabel, dayNumber, duration, fromMin, h, icon, longDayLabel, money, nowMinutesIn, plural, readTimeInput, timeInput,
  signedMoney, todayIn, toMin, weekdayShort,
} from '../util.js';
import { store } from '../store.js';
import { avatar, confirmDialog, emptyState, field, openSheet, spinner, toast, withBusy } from '../ui.js';
import { openScheduleEditor, openScheduleRulesPicker } from '../schedule-editor.js';

const STRIP_DAYS = 28;
const CELL_H = 84;
const LANE_GAP = 10;
const ADD_W = 84;
/** px per minute on timeline: 1ч ≈ 168px (2.8), 45м ≈ 126px, 30м ≈ 84px — readable on scroll */
const PX_PER_MIN_MOBILE = 2.55;
const PX_PER_MIN_DESKTOP = 2.85;
const APPT_COMPACT_W = 92;
const ROW_TRACK_H = 72;
/** Левая колонка имён — шкала времени начинается справа от неё */
const TIMELINE_LABEL_W = 148;

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
    if (manager && data) {
      const schedCells = (data.cells || []).filter((c) => c.schedule_window);
      if (schedCells.length) {
        nav.append(
          h(
            'button',
            { class: 'btn sm', type: 'button', onclick: () => openRulesPicker(schedCells) },
            icon('calendar'),
            'Смены и правила',
          ),
        );
      }
      if (shiftCells().length) {
        nav.append(
          h(
            'button',
            {
              class: 'btn primary sm',
              type: 'button',
              onclick: () => loadCatalog().then((cat) => openManualBooking(null, cat)),
            },
            icon('plus'),
            'Ручная запись',
          ),
        );
      }
    }
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

  function cellEndMin(c) {
    return c.end === '24:00' ? 1440 : toMin(c.end);
  }

  function timeScale(cells) {
    let startMin = Math.floor(toMin(data.work_start) / 60) * 60;
    let endMin = Math.ceil(toMin(data.work_end) / 60) * 60;
    for (const c of cells) {
      startMin = Math.min(startMin, Math.floor(toMin(c.start) / 60) * 60);
      endMin = Math.max(endMin, Math.ceil(cellEndMin(c) / 60) * 60);
    }
    const pxm = window.innerWidth < 720 ? PX_PER_MIN_MOBILE : PX_PER_MIN_DESKTOP;
    return { startMin, endMin, pxm };
  }

  function buildApptBlock(b, cell, startMin, pxm) {
    const bs = toMin(b.start);
    const be = toMin(b.end);
    const bw = Math.max((be - bs) * pxm - 3, 24);
    const bl = (bs - startMin) * pxm;
    const title = `${b.start}–${b.end} · ${b.client_name || 'Клиент'} · ${(b.service_names || []).join(', ')}`;
    const compact = bw < APPT_COMPACT_W;
    const mid = !compact && bw < APPT_COMPACT_W + 48;
    const kids = compact
      ? [h('span', { class: 'appt-glyph', 'aria-hidden': 'true' }, '📋')]
      : [
          h('span', { class: 'appt-time num' }, `${b.start}–${b.end}`),
          mid ? null : h('span', { class: 'appt-who' }, b.client_name || 'Клиент'),
        ];
    return h(
      'button',
      {
        class: `appt-block${compact ? ' compact' : mid ? ' slim' : ''}`,
        type: 'button',
        style: { left: `${bl}px`, width: `${bw}px` },
        title,
        'aria-label': title,
        onclick: () => openBookingDetail(b, cell),
      },
      kids,
    );
  }

  function renderBar() {
    const cells = data.cells || [];
    const scheduleCells = cells.filter((c) => c.schedule_window).sort((a, b) => a.staff.name.localeCompare(b.staff.name, 'ru'));
    const legacyCells = cells.filter((c) => !c.schedule_window);
    if (!cells.length && !manager) {
      barCard.replaceChildren(emptyState('🗓️', 'В этот день смены нет', scope === 'own' ? 'По графику вы не работаете в этот день.' : 'Никто из мастеров не работает в этот день.'));
      return;
    }

    const { startMin, endMin, pxm } = timeScale(cells);
    const baseWidth = (endMin - startMin) * pxm;
    const width = Math.max(baseWidth, 320);

    const ticks = h('div', { class: 'ticks staff-ticks' });
    for (let m = startMin; m <= endMin; m += 60) {
      const x = (m - startMin) * pxm;
      ticks.append(h('span', { class: `tick ${m === startMin ? 'first' : ''}`, style: { left: `${x}px` } }, fromMin(m % 1440 === 0 && m > 0 ? 0 : m)));
    }
    const tickStrip = h('div', { class: 'tick-strip' }, h('span', { class: 'tick-gutter', 'aria-hidden': 'true' }), ticks);

    const rows = h('div', { class: 'staff-rows' });
    for (const cell of scheduleCells) {
      const s = toMin(cell.start);
      const e = cellEndMin(cell);
      const rowHead = h(
        'div',
        { class: 'staff-row-head' },
        avatar(cell.staff, 'sm'),
        h('div', { class: 'staff-row-meta' }, h('b', null, cell.staff.name), h('span', { class: 'small muted num' }, `${cell.start}–${cell.end} · свободно ${duration(cell.free_minutes)}`)),
        manager
          ? h(
              'div',
              { class: 'row wrap', style: { gap: '6px', marginLeft: 'auto' } },
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => openScheduleEditor(cell.staff.id, { anchorDate: date, onSaved: () => load() }) }, icon('calendar'), 'График'),
              cell.free_minutes > 0
                ? h('button', { class: 'btn sm primary', type: 'button', onclick: () => loadCatalog().then((cat) => openManualBooking(cell, cat)) }, icon('plus'), 'Запись')
                : null,
            )
          : null,
      );

      const track = h('div', { class: 'staff-track', style: { height: `${ROW_TRACK_H}px`, width: `${width}px` } });
      track.append(
        h('i', {
          class: 'shift-band',
          style: { left: `${(s - startMin) * pxm}px`, width: `${(e - s) * pxm}px` },
          'aria-hidden': 'true',
        }),
      );
      if (date === today) {
        const nowMin = nowMinutesIn(tz);
        if (nowMin >= startMin && nowMin <= endMin) {
          track.append(h('i', { class: 'now-line', style: { left: `${(nowMin - startMin) * pxm}px` } }));
        }
      }
      for (let m = startMin; m <= endMin; m += 60) {
        track.append(h('i', { class: 'gridline', style: { left: `${(m - startMin) * pxm}px` } }));
      }

      for (const b of cell.bookings || []) {
        track.append(buildApptBlock(b, cell, startMin, pxm));
      }

      rows.append(h('section', { class: 'staff-row' }, rowHead, track));
    }

    if (legacyCells.length) {
      rows.append(h('h3', { class: 'legacy-day-title', style: { marginTop: '16px' } }, 'Ручные ячейки'));
      const legacyWrap = renderLegacyLanes(legacyCells, startMin, endMin, pxm);
      rows.append(legacyWrap);
    }

    const timeline = h(
      'div',
      {
        class: 'timeline timeline-staff',
        style: {
          minWidth: `${width + TIMELINE_LABEL_W + 40}px`,
          '--timeline-label-w': `${TIMELINE_LABEL_W}px`,
        },
      },
      tickStrip,
      rows,
    );
    const scroller = h('div', { class: 'timeline-scroll' }, timeline);
    const legend = h(
      'div',
      { class: 'legend' },
      h('span', null, h('i', { class: 'leg-shift' }), 'Рабочее окно'),
      h('span', null, h('i', { class: 'leg-appt' }), 'Запись'),
    );
    barCard.replaceChildren(scroller, legend);
    requestAnimationFrame(() => {
      const target = date === today ? (nowMinutesIn(tz) - startMin) * pxm - 80 : 0;
      scroller.scrollLeft = Math.max(0, target);
    });
  }

  function renderLegacyLanes(legacyCells, startMin, endMin, pxm) {
    const { placed, lanes } = layoutLanes(legacyCells);
    const lanesHeight = lanes * (CELL_H + LANE_GAP) - LANE_GAP;
    const wrap = h('div', { class: 'lanes legacy-lanes', style: { height: `${lanesHeight}px`, width: `${(endMin - startMin) * pxm}px`, position: 'relative' } });
    for (const { cell, lane, s, e } of placed) {
      const w = (e - s) * pxm - 4;
      const left = (s - startMin) * pxm;
      wrap.append(
        h(
          'button',
          {
            class: `cell s-${cell.status}`,
            type: 'button',
            style: { left: `${left}px`, top: `${lane * (CELL_H + LANE_GAP)}px`, width: `${w}px` },
            title: `${cell.start}–${cell.end}, ${cell.staff.name}`,
            onclick: () => openCellModal(cell),
          },
          h('div', { class: 'c-time' }, `${cell.start}–${cell.end}`),
          h('div', { class: 'c-who' }, avatar(cell.staff, 'sm'), h('span', null, cell.staff.name)),
        ),
      );
    }
    if (manager) {
      const lastEnd = placed.reduce((m, p) => Math.max(m, p.e), 0);
      wrap.append(
        h('button', {
          class: 'cell-add',
          type: 'button',
          style: { left: `${(Math.max(lastEnd, startMin) - startMin) * pxm + 10}px`, top: '0' },
          onclick: () => openCellForm(null, { suggestStart: Math.max(lastEnd, toMin(data.work_start)) }),
        }, icon('plus')),
      );
    }
    return wrap;
  }

  function openRulesPicker(schedCells) {
    const uniq = [];
    const seen = new Set();
    for (const c of schedCells) {
      if (!seen.has(c.staff.id)) {
        seen.add(c.staff.id);
        uniq.push({ id: c.staff.id, name: c.staff.name });
      }
    }
    openScheduleRulesPicker(uniq, { anchorDate: date, onSaved: () => load() });
  }

  function openBookingDetail(booking, cell) {
    const mins = Math.max(0, toMin(booking.end) - toMin(booking.start));
    openSheet({
      title: 'Запись',
      build: (sheet) => {
        sheet.body.append(
          h('div', { class: 'hero' }, avatar(cell.staff, 'lg'), h('h2', null, booking.client_name || 'Клиент'), h('p', { class: 'num muted' }, `${booking.start}–${booking.end} · ${duration(mins)}`)),
          h('dl', { class: 'kv' },
            h('dt', null, 'Мастер'), h('dd', null, cell.staff.name),
            h('dt', null, 'Услуги'), h('dd', null, (booking.service_names || []).join(', ') || '—'),
            booking.client_phone ? h('dt', null, 'Телефон') : null,
            booking.client_phone ? h('dd', null, h('a', { href: `tel:+${booking.client_phone}` }, `+${booking.client_phone}`)) : null,
            booking.comment ? h('dt', null, 'Комментарий') : null,
            booking.comment ? h('dd', null, booking.comment) : null,
            h('dt', null, 'Сумма'), h('dd', null, money(booking.total_price_cents)),
            h('dt', null, 'Статус'), h('dd', null, BOOKING_STATUS[booking.status] || booking.status),
          ),
        );
        sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'));
      },
    });
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
        } else if (manager && cell.schedule_window && cell.free_minutes > 0) {
          sheet.setFooter(
            h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'),
            h('button', { class: 'btn primary', type: 'button', onclick: () => { sheet.close(); openManualBooking(cell, cat); } }, icon('plus'), 'Записать клиента'),
          );
        } else {
          sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'));
        }
      },
    });
  }

  function shiftCells() {
    return (data?.cells || []).filter((c) => c.schedule_window && c.free_minutes > 0);
  }

  function shiftForStaff(staffId) {
    return (data?.cells || []).find((c) => c.schedule_window && c.staff.id === staffId);
  }

  function freeIntervals(cell) {
    const start = toMin(cell.start);
    const end = cell.end === '24:00' ? 1440 : toMin(cell.end);
    let segs = [{ s: start, e: end }];
    for (const b of cell.bookings || []) {
      const bs = toMin(b.start);
      const be = toMin(b.end);
      const next = [];
      for (const seg of segs) {
        if (be <= seg.s || bs >= seg.e) {
          next.push(seg);
          continue;
        }
        if (bs > seg.s) next.push({ s: seg.s, e: bs });
        if (be < seg.e) next.push({ s: be, e: seg.e });
      }
      segs = next;
    }
    return segs.filter((seg) => seg.e > seg.s);
  }

  function slotStartsForCell(cell, step, needMin) {
    const slots = [];
    for (const { s, e } of freeIntervals(cell)) {
      let t = s;
      if (step > 1) t = Math.ceil(t / step) * step;
      for (; t + needMin <= e; t += step) slots.push(fromMin(t));
    }
    return slots;
  }

  function totalMinutesForIds(catalog, ids) {
    return catalog.services.filter((s) => ids.has(s.id)).reduce((n, s) => n + (s.duration_minutes || 0), 0);
  }

  function totalBlockMinutesForIds(catalog, ids) {
    return catalog.services
      .filter((s) => ids.has(s.id))
      .reduce((n, s) => n + (s.duration_minutes || 0) + (s.buffer_minutes || 0), 0);
  }

  function endSlotsForStart(cell, start, minBlock, step) {
    if (!start) return [];
    const startM = toMin(start);
    const interval = freeIntervals(cell).find((seg) => startM >= seg.s && startM < seg.e);
    if (!interval) return [];
    const minEnd = startM + minBlock;
    const slots = [];
    let t = minEnd;
    if (step > 1) t = Math.ceil(t / step) * step;
    if (t < minEnd) t = minEnd;
    for (; t <= interval.e; t += step) slots.push(fromMin(t));
    return slots;
  }

  function servicesForStaff(catalog, staffId) {
    return catalog.services.filter(
      (s) => s.is_active && (!s.staff_ids?.length || s.staff_ids.includes(staffId)),
    );
  }

  function openManualBooking(cell, catalog) {
    const shifts = shiftCells();
    if (!shifts.length) {
      toast('На этот день нет свободного времени у мастеров');
      return;
    }
    const gridStep = store.info?.grid_step_minutes || 30;
    const chosen = new Set();
    const name = h('input', { class: 'input', type: 'text', maxlength: '120', placeholder: 'ФИО клиента' });
    const phone = h('input', { class: 'input', type: 'tel', inputmode: 'tel', placeholder: '+7 900 000-00-00' });
    const comment = h('textarea', { class: 'textarea', maxlength: '500', placeholder: 'Комментарий' });
    const error = h('p', { class: 'small', style: { color: 'var(--bad)' } });
    const staffSelect = h('select', { class: 'input select' });
    const startSelect = h('select', { class: 'input select' });
    const endSelect = h('select', { class: 'input select' });
    const intervalHint = h('p', { class: 'small muted' });
    const shiftHint = h('p', { class: 'small muted' });
    const svcWrap = h('div', { class: 'col' });
    let activeStaffId = cell?.staff?.id || shifts[0].staff.id;
    let endTouched = false;

    for (const c of shifts) {
      staffSelect.append(h('option', { value: c.staff.id }, c.staff.name));
    }

    const dateChip = h('span', { class: 'chip active' }, dayLabel(date));

    function activeShift() {
      return shiftForStaff(activeStaffId);
    }

    function refreshServices() {
      chosen.forEach((id) => {
        const ok = servicesForStaff(catalog, activeStaffId).some((s) => s.id === id);
        if (!ok) chosen.delete(id);
      });
      svcWrap.replaceChildren();
      for (const s of servicesForStaff(catalog, activeStaffId)) {
        const on = h('input', { class: 'check', type: 'checkbox', checked: chosen.has(s.id) });
        on.addEventListener('change', () => {
          if (on.checked) chosen.add(s.id);
          else chosen.delete(s.id);
          refreshTiming();
        });
        svcWrap.append(
          h(
            'label',
            { class: 'row' },
            on,
            h('span', null, s.name),
            h('span', { class: 'small muted' }, duration(s.duration_minutes)),
          ),
        );
      }
      if (!svcWrap.childNodes.length) {
        svcWrap.append(h('p', { class: 'small muted' }, 'Нет услуг для выбранного мастера.'));
      }
    }

    function defaultEndForStart(start) {
      const block = chosen.size ? totalBlockMinutesForIds(catalog, chosen) : gridStep;
      return fromMin(toMin(start) + Math.max(block, gridStep));
    }

    function refreshTiming() {
      const shift = activeShift();
      if (!shift) return;
      const block = Math.max(chosen.size ? totalBlockMinutesForIds(catalog, chosen) : gridStep, gridStep);
      const slots = slotStartsForCell(shift, gridStep, block);
      const prevStart = startSelect.value;
      const prevEnd = endSelect.value;
      startSelect.replaceChildren();
      if (!slots.length) {
        startSelect.append(h('option', { value: '' }, 'Нет слотов под выбранные услуги'));
        startSelect.disabled = true;
        endSelect.disabled = true;
        endSelect.replaceChildren(h('option', { value: '' }, '—'));
      } else {
        startSelect.disabled = false;
        for (const t of slots) startSelect.append(h('option', { value: t }, t));
        let pick = prevStart;
        if (cell && cell.staff.id === activeStaffId && slots.includes(cell.start)) pick = cell.start;
        if (!pick || !slots.includes(pick)) pick = slots[0];
        startSelect.value = pick;
      }
      shiftHint.textContent = `Смена мастера: ${shift.start}–${shift.end}`;
      const start = startSelect.value;
      if (!start) {
        intervalHint.textContent = '';
        return;
      }
      const endSlots = endSlotsForStart(shift, start, chosen.size ? totalBlockMinutesForIds(catalog, chosen) : gridStep, gridStep);
      endSelect.replaceChildren();
      if (!endSlots.length) {
        endSelect.append(h('option', { value: '' }, 'Нет места до конца смены'));
        endSelect.disabled = true;
      } else {
        endSelect.disabled = false;
        for (const t of endSlots) endSelect.append(h('option', { value: t }, t));
        let endPick = endTouched && prevEnd && endSlots.includes(prevEnd) ? prevEnd : defaultEndForStart(start);
        if (!endSlots.includes(endPick)) endPick = endSlots[endSlots.length - 1];
        endSelect.value = endPick;
      }
      const end = endSelect.value;
      if (end && chosen.size) {
        const mins = toMin(end) - toMin(start);
        intervalHint.textContent = `Интервал: ${start}–${end} (${duration(mins)}; услуги ${duration(totalMinutesForIds(catalog, chosen))})`;
      } else if (start) {
        intervalHint.textContent = 'Выберите услуги — подставим конец по каталогу, можно удлинить.';
      }
    }

    staffSelect.value = activeStaffId;
    staffSelect.addEventListener('change', () => {
      activeStaffId = staffSelect.value;
      endTouched = false;
      refreshServices();
      refreshTiming();
    });
    startSelect.addEventListener('change', () => {
      endTouched = false;
      refreshTiming();
    });
    endSelect.addEventListener('change', () => {
      endTouched = true;
      refreshTiming();
    });

    openSheet({
      title: 'Ручная запись',
      build: (sheet) => {
        refreshServices();
        refreshTiming();
        sheet.body.append(
          field('Дата', dateChip),
          field('Мастер', staffSelect),
          h('div', { class: 'grid2' }, field('Начало', startSelect), field('Конец', endSelect)),
          h('div', { class: 'col', style: { gap: '4px' } }, intervalHint, shiftHint),
          field('Услуги', svcWrap),
          field('Клиент', name),
          field('Телефон', phone),
          field('Комментарий', comment),
          error,
        );
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Создать запись');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            error.textContent = '';
            const shift = activeShift();
            if (!shift) {
              error.textContent = 'Выберите мастера со свободной сменой.';
              return;
            }
            if (!name.value.trim() || phone.value.replace(/\D/g, '').length < 10) {
              error.textContent = 'Укажите имя и полный телефон.';
              return;
            }
            if (!chosen.size) {
              error.textContent = 'Выберите хотя бы одну услугу.';
              return;
            }
            const startTime = startSelect.value;
            const endTime = endSelect.value;
            if (!startTime) {
              error.textContent = 'Выберите время начала в свободном окне смены.';
              return;
            }
            if (!endTime || toMin(endTime) <= toMin(startTime)) {
              error.textContent = 'Выберите конец интервала позже начала.';
              return;
            }
            try {
              await api.post('/manager/bookings/manual', {
                staff_member_id: activeStaffId,
                date: shift.date,
                start_time: startTime,
                end_time: endTime,
                service_ids: [...chosen],
                client_name: name.value.trim(),
                client_phone: phone.value.trim(),
                comment: comment.value.trim() || null,
              });
              sheet.close();
              toast('Запись создана');
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
        const startInput = timeInput({ value: state.start, required: true });
        const endInput = timeInput({ value: state.end === '24:00' ? '24:00' : state.end, required: true });
        const priceInput = h('input', { class: 'input', type: 'number', step: '50', inputmode: 'decimal', placeholder: '0', value: editing && cell.price_cents ? cell.price_cents / 100 : '' });
        const titleInput = h('input', { class: 'input', type: 'text', maxlength: '255', placeholder: 'Например, «Вечернее окно»', value: editing ? cell.title || '' : '' });
        const descInput = h('textarea', { class: 'textarea', maxlength: '2000', placeholder: 'Что важно знать клиенту' }, editing ? cell.description || '' : '');
        const durLabel = h('span', { class: 'small muted' });
        const error = h('p', { class: 'small', style: { color: 'var(--bad)' }, role: 'alert' });

        const updateDur = () => {
          const d = toMin(readTimeInput(endInput) || '00:00') - toMin(readTimeInput(startInput) || '00:00');
          durLabel.textContent = d > 0 ? `Длительность: ${duration(d)}` : 'Конец должен быть позже начала';
        };
        let lastDur = Math.max(5, toMin(readTimeInput(endInput) || '00:00') - toMin(readTimeInput(startInput) || '00:00'));
        startInput.addEventListener('change', () => {
          const e = Math.min(toMin(readTimeInput(startInput) || '00:00') + lastDur, 24 * 60 - 1);
          endInput.value = fromMin(e);
          updateDur();
        });
        endInput.addEventListener('change', () => {
          const d = toMin(readTimeInput(endInput) || '00:00') - toMin(readTimeInput(startInput) || '00:00');
          if (d > 0) lastDur = d;
          updateDur();
        });
        updateDur();

        const quick = h(
          'div',
          { class: 'chips' },
          [30, 60, 90, 120, 180, 240].map((m) =>
            h('button', { class: 'chip', type: 'button', onclick: () => {
              endInput.value = fromMin(Math.min(toMin(readTimeInput(startInput) || '00:00') + m, 24 * 60 - 1));
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
              start: readTimeInput(startInput),
              end: readTimeInput(endInput),
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
