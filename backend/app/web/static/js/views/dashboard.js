import { api, friendly } from '../api.js';
import { addDays, chartPalette, h, money, rgbaFromRgb, todayIn } from '../util.js';
import { store } from '../store.js';
import { emptyState, field, spinner } from '../ui.js';
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

function pieDonut(segments, size = 168) {
  const withData = segments.filter((s) => s.value > 0);
  const total = withData.reduce((s, x) => s + x.value, 0);
  if (!total) {
    return h('div', { class: 'dash-pie-empty muted small' }, 'Нет записей за период');
  }
  let acc = 0;
  const stops = [];
  for (const seg of withData) {
    const pct = (100 * seg.value) / total;
    const from = acc;
    acc += pct;
    stops.push(`${seg.color} ${from}% ${acc}%`);
  }
  const ring = h('div', {
    class: 'dash-pie-donut',
    style: {
      width: `${size}px`,
      height: `${size}px`,
      background: `conic-gradient(from -90deg, ${stops.join(', ')})`,
    },
    role: 'img',
    'aria-label': 'Структура записей',
  });
  const totalLabel = h('div', { class: 'dash-pie-center' }, h('b', { class: 'num' }, String(total)), h('span', { class: 'tiny muted' }, 'записей'));
  return h('div', { class: 'dash-pie-wrap', style: { width: `${size}px`, height: `${size}px` } }, ring, totalLabel);
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
  const scheduleMount = h('div', { class: 'dash-schedule' });
  const analyticsHead = h('h2', { class: 'dash-analytics-title', style: { margin: '16px 0 8px' } }, 'Аналитика');
  const rangeBar = h('div', { class: 'row wrap', style: { gap: '8px', marginBottom: '12px' } });
  const kpiRow = h('div', { class: 'stats' });
  const pieWrap = h('div', { class: 'card pad col', style: { gap: '10px' } });
  const chartsRow = h('div', { class: 'dash-charts' });

  let range = { from: addDays(today, -29), to: today };
  let granularity = 'day';
  let chartResizeObserver = null;

  const presets = [
    { id: 'all', label: 'За всё время', from: '2020-01-01', to: today },
    { id: 'today', label: 'Сегодня', from: today, to: today },
    { id: '7d', label: '7 дней', from: addDays(today, -6), to: today },
    { id: '30d', label: 'Месяц', from: addDays(today, -29), to: today },
  ];

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
      ];
      const total = segments.reduce((s, x) => s + x.value, 0);
      pieWrap.replaceChildren(
        h('h2', null, 'Структура записей'),
        h('div', { class: 'row wrap', style: { gap: '16px', alignItems: 'center' } }, pieDonut(segments), h('div', { class: 'col grow', style: { gap: '6px' } }, ...segments.map((s) => legendRow(s, total)))),
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

  function resizeMountedCharts() {
    chartsRow.querySelectorAll('.dash-chart').forEach((el) => {
      const chart = el.__chart;
      const w = el.clientWidth;
      if (chart && w > 0) {
        chart.applyOptions({ width: w });
        chart.timeScale().fitContent();
      }
    });
  }

  async function renderCharts() {
    chartsRow.replaceChildren(h('div', { class: 'card pad' }, spinner()));
  chartResizeObserver?.disconnect();
    try {
      const L = await loadLightweightCharts();
      const [bookings, revenue] = await Promise.all([
        api.get(`/manager/analytics/series?from=${range.from}&to=${range.to}&granularity=${granularity}&metric=bookings`),
        api.get(`/manager/analytics/series?from=${range.from}&to=${range.to}&granularity=${granularity}&metric=revenue`),
      ]);
      chartsRow.replaceChildren();
      mountChart(chartsRow, L, 'Записи', bookings.points, false, granularity);
      mountChart(chartsRow, L, 'Выручка', revenue.points, true, granularity);
      chartResizeObserver = new ResizeObserver(() => resizeMountedCharts());
      chartsRow.querySelectorAll('.dash-chart').forEach((el) => chartResizeObserver.observe(el));
      requestAnimationFrame(() => requestAnimationFrame(resizeMountedCharts));
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
    const el = h('div', { class: 'dash-chart', style: { height: '220px', width: '100%', minWidth: '0' } });
    wrap.append(el);
    parent.append(wrap);
    const { text: textColor, gold } = chartPalette();
    let chart;
    try {
      const initialW = Math.max(el.clientWidth || parent.clientWidth || 0, 280);
      chart = L.createChart(el, {
        width: initialW,
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
      el.__chart = chart;
    } catch (e) {
      wrap.replaceChildren(h('p', { class: 'small muted' }, 'График не удалось отрисовать'));
      console.warn('chart render failed', e);
      return null;
    }
    return chart;
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
    h('div', { class: 'page-head' }, h('div', null, h('h1', null, 'Дашборд'), h('p', { class: 'muted' }, 'Расписание и статистика салона'))),
    scheduleMount,
    analyticsHead,
    rangeBar,
    kpiRow,
    h('div', { class: 'dash-grid' }, pieWrap, h('div', { class: 'col' }, gran, chartsRow)),
  );

  if (sub === 'schedule') {
    /* hash only; schedule always shown */
  }

  scheduleMount.replaceChildren(dayView({ manager: true, embedded: true }));

  chartsRow.replaceChildren(h('div', { class: 'card pad' }, spinner()));
  await renderSummary();

  root.afterMount = async () => {
    await renderCharts();
    requestAnimationFrame(() => requestAnimationFrame(resizeMountedCharts));
  };

  root.cleanup = () => chartResizeObserver?.disconnect();

  return root;
}