import { api, friendly } from '../api.js';
import { addDays, chartPalette, duration, h, icon, money, rgbaFromRgb, todayIn } from '../util.js';
import { store } from '../store.js';
import { emptyState, field, spinner, toast, withBusy } from '../ui.js';
import { dayView } from './day.js';

function loadLightweightCharts() {
  return new Promise((resolve, reject) => {
    if (window.LightweightCharts) {
      resolve(window.LightweightCharts);
      return;
    }
    const s = document.createElement('script');
    s.src = 'https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js';
    s.async = true;
    s.onload = () => resolve(window.LightweightCharts);
    s.onerror = () => reject(new Error('charts load failed'));
    document.head.appendChild(s);
  });
}

function pieSvg(segments, size = 168) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r = size / 2 - 6;
  const cx = size / 2;
  const cy = size / 2;
  let acc = -Math.PI / 2;
  const paths = [];
  for (const seg of segments) {
    if (seg.value <= 0) continue;
    const slice = (seg.value / total) * Math.PI * 2;
    const x1 = cx + r * Math.cos(acc);
    const y1 = cy + r * Math.sin(acc);
    acc += slice;
    const x2 = cx + r * Math.cos(acc);
    const y2 = cy + r * Math.sin(acc);
    const large = slice > Math.PI ? 1 : 0;
    paths.push(
      h('path', {
        d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`,
        fill: seg.color,
        opacity: 0.92,
      }),
    );
  }
  return h('svg', { class: 'dash-pie', width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: 'img' }, ...paths);
}

function formatBlockRange(b) {
  const fromD = b.start_date || b.date || '';
  const toD = b.end_date || fromD;
  const st = b.start || '';
  const en = b.end || '';
  if (!fromD) return `${st}–${en}`;
  if (fromD === toD) return `${fromD} ${st}–${en}`;
  return `${fromD} ${st} – ${toD} ${en}`;
}

function legendRow(seg, total) {
  const pct = total ? Math.round((100 * seg.value) / total) : 0;
  return h(
    'div',
    { class: 'row between small' },
    h('span', null, h('i', { class: 'dash-dot', style: { background: seg.color } }), seg.label),
    h('b', { class: 'num' }, `${seg.value} · ${pct}%`),
  );
}

export async function dashboardView(sub = '') {
  const tz = store.info?.timezone;
  const today = todayIn(tz);
  const root = h('div', { class: 'dashboard' });
  const rangeBar = h('div', { class: 'row wrap', style: { gap: '8px', marginBottom: '12px' } });
  const kpiRow = h('div', { class: 'stats' });
  const pieWrap = h('div', { class: 'card pad col', style: { gap: '10px' } });
  const chartsRow = h('div', { class: 'dash-charts' });
  const blocksCard = h('div', { class: 'card pad col' });
  const scheduleMount = h('div', { class: 'dash-schedule' });
  /** @type {HTMLElement & { reload?: () => void }} | null */
  let scheduleView = null;

  function refreshEmbeddedSchedule() {
    scheduleView?.reload?.();
  }

  let range = { from: addDays(today, -29), to: today };
  let granularity = 'day';

  const presets = [
    { id: 'all', label: 'За всё время', from: '2020-01-01', to: today },
    { id: 'today', label: 'Сегодня', from: today, to: today },
    { id: '7d', label: '7 дней', from: addDays(today, -6), to: today },
    { id: '30d', label: 'Месяц', from: addDays(today, -29), to: today },
  ];

  let chartBook = null;
  let chartRev = null;

  async function renderSummary() {
    kpiRow.replaceChildren(spinner());
    pieWrap.replaceChildren(spinner());
    try {
      const data = await api.get(`/manager/analytics/summary?from=${range.from}&to=${range.to}`);
      const c = data.counts;
      kpiRow.replaceChildren(
        stat(c.completed, 'Услуг оказано'),
        stat(money(data.revenue_cents), 'Выручка'),
        stat(c.upcoming, 'Предстоит'),
        stat(c.cancelled, 'Отменено'),
        stat(`${c.utilization_percent}%`, 'Загрузка'),
        stat(money(data.avg_ticket_cents), 'Средний чек'),
      );
      const segments = [
        { label: 'Успешно', value: c.completed, color: 'var(--ok)' },
        { label: 'Отменено', value: c.cancelled, color: 'var(--bad)' },
        { label: 'Предстоит', value: c.upcoming, color: 'var(--ui-gold)' },
        { label: 'Свободно (мин)', value: c.free_minutes, color: 'var(--muted)' },
      ];
      const total = segments.reduce((s, x) => s + x.value, 0);
      pieWrap.replaceChildren(
        h('h2', null, 'Структура записей'),
        h('div', { class: 'row wrap', style: { gap: '16px', alignItems: 'center' } }, pieSvg(segments), h('div', { class: 'col grow', style: { gap: '6px' } }, ...segments.map((s) => legendRow(s, total)))),
        data.top_services?.length
          ? h('div', null, h('h3', { class: 'small muted' }, 'Топ услуг'), ...data.top_services.map((s) => h('div', { class: 'row between small' }, h('span', null, s.name), h('b', null, s.count))))
          : null,
        data.staff_completed?.length
          ? h('div', { style: { marginTop: '8px' } }, h('h3', { class: 'small muted' }, 'Мастера (оказано)'), ...data.staff_completed.slice(0, 5).map((s) => h('div', { class: 'row between small' }, h('span', null, s.name), h('b', null, s.count))))
          : null,
      );
    } catch (e) {
      kpiRow.replaceChildren(emptyState('⚠️', 'Нет данных', friendly(e)));
      pieWrap.replaceChildren();
    }
  }

  const stat = (value, label) => h('div', { class: 'card stat' }, h('b', null, value), h('span', null, label));

  async function renderCharts() {
    chartsRow.replaceChildren(h('div', { class: 'card pad' }, spinner()));
    try {
      const L = await loadLightweightCharts();
      const [bookings, revenue] = await Promise.all([
        api.get(`/manager/analytics/series?from=${range.from}&to=${range.to}&granularity=${granularity}&metric=bookings`),
        api.get(`/manager/analytics/series?from=${range.from}&to=${range.to}&granularity=${granularity}&metric=revenue`),
      ]);
      chartsRow.replaceChildren();
      chartBook = mountChart(chartsRow, L, 'Записи', bookings.points, false, granularity);
      chartRev = mountChart(chartsRow, L, 'Выручка', revenue.points, true, granularity);
    } catch (e) {
      chartsRow.replaceChildren(emptyState('📈', 'Графики недоступны', friendly(e)));
    }
  }

  function chartTime(period, idx, gran) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(period)) return period;
    const step = gran === 'week' ? 7 : gran === 'month' ? 30 : 1;
    return addDays(range.from, idx * step);
  }

  function mountChart(parent, L, title, points, isMoney, gran) {
    const wrap = h('div', { class: 'card pad dash-chart-card' });
    wrap.append(h('h3', null, title));
    const el = h('div', { class: 'dash-chart', style: { height: '220px' } });
    wrap.append(el);
    parent.append(wrap);
    const { text: textColor, gold } = chartPalette();
    let chart;
    try {
      chart = L.createChart(el, {
      layout: { background: { color: 'transparent' }, textColor },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
        handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      });
      const series = chart.addAreaSeries({
        lineColor: gold,
        topColor: rgbaFromRgb(gold, 0.35),
        bottomColor: 'transparent',
      });
      const data = points.map((p, i) => ({
        time: chartTime(p.period, i, gran),
        value: isMoney ? p.value / 100 : p.value,
      }));
      series.setData(data.length ? data : [{ time: range.to, value: 0 }]);
      chart.timeScale().fitContent();
    } catch (e) {
      wrap.replaceChildren(h('p', { class: 'small muted' }, 'График не удалось отрисовать'));
      console.warn('chart render failed', e);
      return null;
    }
    return chart;
  }

  async function renderBlocks() {
    blocksCard.replaceChildren(spinner());
    try {
      const [blocks, staff] = await Promise.all([
        api.get(`/manager/blocks?from=${addDays(today, -7)}&days=120`),
        api.get('/manager/staff'),
      ]);
      const staffOpts = staff.filter((s) => s.is_active !== false);
      const startDate = field({ label: 'Начало (дата)', tag: 'input', props: { type: 'date', value: today } });
      const startTime = field({ label: 'Время', tag: 'input', props: { type: 'time', value: '10:00' } });
      const endDate = field({ label: 'Конец (дата)', tag: 'input', props: { type: 'date', value: today } });
      const endTime = field({ label: 'Время', tag: 'input', props: { type: 'time', value: '18:00' } });
      const note = field({ label: 'Комментарий', tag: 'input', props: { maxlength: 200, placeholder: 'Технический перерыв' } });
      const staffPick = h('div', { class: 'chips wrap blocks-staff' });
      for (const s of staffOpts) {
        const cb = h('input', { type: 'checkbox', class: 'check', checked: true, value: String(s.id) });
        staffPick.append(h('label', { class: 'chip blocks-staff-chip' }, cb, s.name));
      }
      const list = h('div', { class: 'list', style: { marginTop: '10px' } });
      const paintList = () => {
        const items = blocks.items || [];
        if (!items.length) {
          list.replaceChildren(h('p', { class: 'muted small' }, 'Блокировок нет.'));
          return;
        }
        list.replaceChildren(
          ...items.map((b) => h(
            'article',
            { class: 'card pad row between' },
            h('div', null, h('b', null, b.staff_name || 'Мастер'), h('div', { class: 'small muted num' }, `${formatBlockRange(b)} · ${b.note || ''}`)),
            h('button', {
              class: 'btn sm danger',
              type: 'button',
              onclick: async () => {
                try {
                  await api.delete(`/manager/staff/${b.staff_member_id}/exceptions/${b.id}`);
                  toast('Блокировка снята');
                  blocks.items = (blocks.items || []).filter((x) => x.id !== b.id);
                  paintList();
                  await renderSummary();
                  refreshEmbeddedSchedule();
                } catch (e) {
                  toast(friendly(e), true);
                }
              },
            }, 'Убрать'),
          )),
        );
      };
      paintList();
      const saveBtn = h('button', { class: 'btn primary sm', type: 'button' }, 'Заблокировать');
      saveBtn.addEventListener('click', () => withBusy(saveBtn, async () => {
        const ids = [...staffPick.querySelectorAll('input.check:checked')].map((el) => el.value);
        if (!ids.length) {
          toast('Выберите мастеров', true);
          return;
        }
        const st = startTime.input.value.slice(0, 5);
        const et = endTime.input.value.slice(0, 5);
        try {
          await api.post('/manager/blocks', {
            staff_member_ids: ids,
            start_date: startDate.input.value,
            start_time: st,
            end_date: endDate.input.value,
            end_time: et,
            note: note.input.value.trim() || null,
          });
          toast('Интервал заблокирован');
          const fresh = await api.get(`/manager/blocks?from=${addDays(today, -7)}&days=120`);
          blocks.items = fresh.items;
          paintList();
          await renderSummary();
          refreshEmbeddedSchedule();
        } catch (e) {
          toast(friendly(e), true);
        }
      }));
      blocksCard.replaceChildren(
        h('h2', null, 'Блокировка записи'),
        h('p', { class: 'muted small' }, 'Время недоступно для онлайн-записи и ручного бронирования.'),
        h('div', { class: 'blocks-form' },
          h('div', { class: 'blocks-staff-block' },
            h('span', { class: 'label' }, 'Мастера'),
            staffPick,
          ),
          h('div', { class: 'blocks-range' },
            h('h3', { class: 'blocks-range-title' }, 'Интервал блокировки'),
            h('div', { class: 'blocks-range-row' },
              h('div', { class: 'blocks-range-leg' },
                h('span', { class: 'tiny muted' }, 'С'),
                startDate.el,
                startTime.el,
              ),
              h('div', { class: 'blocks-range-leg' },
                h('span', { class: 'tiny muted' }, 'По'),
                endDate.el,
                endTime.el,
              ),
            ),
          ),
          note.el,
          saveBtn,
        ),
        h('h3', { class: 'blocks-list-title' }, 'Активные блокировки'),
        list,
      );
    } catch (e) {
      blocksCard.replaceChildren(emptyState('⛔', 'Блокировки', friendly(e)));
    }
  }

  function setRange(from, to) {
    range = { from, to };
    renderSummary();
    renderCharts();
  }

  for (const p of presets) {
    const btn = h('button', { class: 'btn sm', type: 'button' }, p.label);
    btn.addEventListener('click', () => {
      rangeBar.querySelectorAll('button.preset').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active', 'preset');
      setRange(p.from, p.to);
    });
    btn.classList.add('preset');
    if (p.id === '30d') btn.classList.add('active');
    rangeBar.append(btn);
  }
  const customFrom = field({ label: 'С', tag: 'input', props: { type: 'date', value: range.from } });
  const customTo = field({ label: 'По', tag: 'input', props: { type: 'date', value: range.to } });
  const applyCustom = h('button', { class: 'btn sm', type: 'button' }, 'Применить');
  applyCustom.addEventListener('click', () => setRange(customFrom.input.value, customTo.input.value));
  rangeBar.append(customFrom.el, customTo.el, applyCustom);

  const gran = h('div', { class: 'chips', style: { margin: '8px 0' } });
  for (const g of ['day', 'week', 'month']) {
    const label = { day: 'Дни', week: 'Недели', month: 'Месяцы' }[g];
    const chip = h('button', { class: `chip ${g === granularity ? 'active' : ''}`, type: 'button' }, label);
    chip.addEventListener('click', () => {
      granularity = g;
      gran.querySelectorAll('.chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      renderCharts();
    });
    gran.append(chip);
  }

  root.append(
    h('div', { class: 'page-head' }, h('div', null, h('h1', null, 'Дашборд'), h('p', { class: 'muted' }, 'Статистика и расписание салона'))),
    rangeBar,
    kpiRow,
    h('div', { class: 'dash-grid' }, pieWrap, h('div', { class: 'col' }, gran, chartsRow)),
    blocksCard,
    h('hr', { style: { margin: '20px 0', border: '0', borderTop: '1px solid var(--line)' } }),
    scheduleMount,
  );

  if (sub === 'schedule') {
    /* hash only; schedule always shown */
  }

  scheduleView = dayView({ manager: true, embedded: true });
  scheduleMount.replaceChildren(scheduleView);

  await Promise.all([renderSummary(), renderCharts(), renderBlocks()]);

  return root;
}