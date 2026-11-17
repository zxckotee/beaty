import { api, friendly } from '../api.js';
import {
  addDays, dayLabel, dayNumber, duration, h, hueFor, icon, initials, longDayLabel, money, plural, signedMoney,
  todayIn, weekdayShort,
} from '../util.js';
import { loadMe, store } from '../store.js';
import { avatar, emptyState, field, openSheet, spinner, toast, withBusy } from '../ui.js';
import { loginPanel } from './login.js';

const SEL_KEY = 'beaty.sel';
let selected = new Set(JSON.parse(sessionStorage.getItem(SEL_KEY) || '[]'));
let staffFilter = null;
let pickedDate = null;

const saveSel = () => sessionStorage.setItem(SEL_KEY, JSON.stringify([...selected]));

function stepsBar(step) {
  const items = ['Услуги', 'Время', 'Запись'];
  const out = [];
  items.forEach((label, i) => {
    if (i) out.push(h('span', { class: 'sep' }));
    out.push(h('span', { class: `s ${i + 1 <= step ? 'on' : ''}` }, h('i', null, i + 1), label));
  });
  return h('div', { class: 'steps' }, out);
}

export async function bookView(sub) {
  const catalog = await api.get('/client/catalog');
  // forget services that no longer exist
  const known = new Set(catalog.services.map((s) => s.id));
  selected = new Set([...selected].filter((id) => known.has(id)));
  saveSel();
  if (sub === 'times' && selected.size) return timesView(catalog);
  return catalogView(catalog);
}

function commonStaff(catalog) {
  const chosen = catalog.services.filter((s) => selected.has(s.id));
  if (!chosen.length) return [];
  let ids = new Set(chosen[0].staff_ids);
  for (const s of chosen.slice(1)) ids = new Set(s.staff_ids.filter((i) => ids.has(i)));
  return catalog.specialists.filter((sp) => ids.has(sp.id));
}

// ---------------- step 1: services ----------------
function catalogView(catalog) {
  const root = h('div');
  const listEl = h('div', { class: 'list two' });
  const cartSlot = h('div');
  let category = null;

  const categories = [...new Set(catalog.services.map((s) => s.category).filter(Boolean))];

  root.append(
    stepsBar(1),
    h('div', { class: 'page-head' }, h('div', null, h('h1', null, 'Выберите услуги'), h('p', null, 'Можно несколько: мы подберём время, в которое всё уместится.'))),
  );

  if (catalog.specialists.length) {
    root.append(
      h(
        'div',
        { class: 'col', style: { marginBottom: '16px' } },
        h('span', { class: 'label' }, 'Наши специалисты'),
        h(
          'div',
          { class: 'chips scroll' },
          catalog.specialists.map((sp) => h('button', { class: 'chip', type: 'button', onclick: () => openSpecialist(sp, catalog) }, avatar(sp, 'sm'), sp.name)),
        ),
      ),
    );
  }

  if (categories.length) {
    const chips = h('div', { class: 'chips scroll', style: { marginBottom: '14px' } });
    const draw = () => {
      chips.replaceChildren(
        h('button', { class: `chip ${category === null ? 'active' : ''}`, type: 'button', onclick: () => { category = null; draw(); drawList(); } }, 'Все'),
        ...categories.map((c) => h('button', { class: `chip ${category === c ? 'active' : ''}`, type: 'button', onclick: () => { category = c; draw(); drawList(); } }, c)),
      );
    };
    draw();
    root.append(chips);
  }

  function drawList() {
    const items = catalog.services.filter((s) => category === null || s.category === category);
    if (!catalog.services.length) {
      listEl.replaceChildren(emptyState('✂️', 'Услуги пока не добавлены', 'Загляните позже.'));
      return;
    }
    listEl.replaceChildren(
      ...items.map((s) => {
        const on = selected.has(s.id);
        const thumb = h('div', { class: 'thumb', style: { '--h': hueFor(s.name) } }, initials(s.name));
        if (s.photo_url) thumb.append(h('img', { src: s.photo_url, alt: '', loading: 'lazy' }));
        return h(
          'button',
          {
            class: `card service-card ${on ? 'on' : ''}`,
            type: 'button',
            'aria-pressed': on,
            onclick: () => {
              if (selected.has(s.id)) selected.delete(s.id);
              else selected.add(s.id);
              saveSel();
              drawList();
              drawCart();
            },
          },
          thumb,
          h(
            'div',
            { class: 'info' },
            h('h3', null, s.name),
            s.description ? h('p', { class: 'small muted clamp2' }, s.description) : null,
            h('div', { class: 'row wrap', style: { marginTop: 'auto' } }, h('b', null, money(s.price_cents)), h('span', { class: 'chip' }, icon('clock'), duration(s.duration_minutes))),
          ),
          h('span', { class: 'check' }, icon('check')),
        );
      }),
    );
  }

  function drawCart() {
    cartSlot.replaceChildren();
    const chosen = catalog.services.filter((s) => selected.has(s.id));
    if (!chosen.length) return;
    const total = chosen.reduce((a, s) => a + s.price_cents, 0);
    const minutes = chosen.reduce((a, s) => a + s.duration_minutes, 0);
    const feasible = commonStaff(catalog).length > 0;
    const go = h('button', { class: 'btn', type: 'button', disabled: !feasible, onclick: () => { location.hash = '#/book/times'; } }, 'Выбрать время', icon('chevR'));
    cartSlot.append(
      h(
        'div',
        { class: 'cart-bar', role: 'region', 'aria-label': 'Выбранные услуги' },
        h('div', { class: 'grow' }, h('b', null, `${chosen.length} ${plural(chosen.length, 'услуга', 'услуги', 'услуг')} · ${duration(minutes)}`), h('div', { class: 'small', style: { opacity: 0.8 } }, feasible ? `от ${money(total)}` : 'Эти услуги не выполняет один мастер')),
        go,
      ),
    );
  }

  drawList();
  drawCart();
  root.append(listEl, cartSlot, h('div', { style: { height: '90px' } }));
  return root;
}

function openSpecialist(sp, catalog) {
  const services = catalog.services.filter((s) => s.staff_ids.includes(sp.id));
  openSheet({
    title: 'Специалист',
    build: (sheet) => {
      sheet.body.append(
        h('div', { class: 'hero' }, avatar(sp, 'xl'), h('h2', null, sp.name), sp.specialization ? h('span', { class: 'chip active' }, sp.specialization) : null, sp.bio ? h('p', { class: 'muted' }, sp.bio) : null),
        services.length ? h('div', { class: 'col' }, h('span', { class: 'label' }, 'Услуги'), h('div', { class: 'chips' }, services.map((s) => h('span', { class: 'chip' }, s.name)))) : null,
      );
      sheet.setFooter(
        h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'),
        h('button', { class: 'btn primary', type: 'button', onclick: () => { staffFilter = sp.id; sheet.close(); toast(`Фильтр: ${sp.name}`); } }, 'Записаться к мастеру'),
      );
    },
  });
}

// ---------------- step 2: times ----------------
async function timesView(catalog) {
  const tz = store.info.timezone;
  const today = todayIn(tz);
  const root = h('div');
  const body = h('div');
  const chosen = catalog.services.filter((s) => selected.has(s.id));
  const eligible = commonStaff(catalog);
  if (staffFilter && !eligible.some((s) => s.id === staffFilter)) staffFilter = null;

  root.append(
    stepsBar(2),
    h(
      'div',
      { class: 'page-head' },
      h('div', null, h('h1', null, 'Выберите время'), h('p', null, 'Свободные интервалы по графику мастера (минус уже занятые записи).')),
      h('button', { class: 'btn sm', type: 'button', onclick: () => { location.hash = '#/book'; } }, icon('chevL'), 'Услуги'),
    ),
    body,
  );

  async function load() {
    body.replaceChildren(spinner());
    let res;
    try {
      res = await api.post('/client/availability', { service_ids: [...selected], staff_member_id: staffFilter });
    } catch (e) {
      body.replaceChildren(emptyState('⚠️', 'Не удалось загрузить окна', friendly(e)));
      return;
    }
    draw(res);
  }

  function draw(res) {
    const byDate = new Map(res.days.map((d) => [d.date, d.offers]));
    const dates = [...byDate.keys()];
    if (!pickedDate || !byDate.has(pickedDate)) pickedDate = dates[0] || null;
    const last = dates.length ? dates[dates.length - 1] : today;
    const span = Math.max(14, Math.round((new Date(`${last}T12:00:00Z`) - new Date(`${today}T12:00:00Z`)) / 86400000) + 1);

    const summary = h(
      'div',
      { class: 'card summary' },
      h('div', { class: 'row between' }, h('b', null, `${duration(res.summary.total_minutes)} · от ${money(res.summary.base_price_cents)}`), h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { location.hash = '#/book'; } }, 'Изменить')),
      h('div', { class: 'chips' }, chosen.map((s) => h('span', { class: 'chip' }, s.name))),
    );

    const who = h(
      'div',
      { class: 'chips scroll', style: { margin: '14px -16px 4px' } },
      h('button', { class: `chip ${staffFilter === null ? 'active' : ''}`, type: 'button', onclick: () => { staffFilter = null; load(); } }, 'Любой специалист'),
      ...eligible.map((s) => h('button', { class: `chip ${staffFilter === s.id ? 'active' : ''}`, type: 'button', onclick: () => { staffFilter = s.id; load(); } }, avatar(s, 'sm'), s.name)),
    );

    const strip = h('div', { class: 'date-strip', role: 'tablist', 'aria-label': 'Даты' });
    for (let i = 0; i < span; i += 1) {
      const d = addDays(today, i);
      const has = byDate.has(d);
      strip.append(
        h(
          'button',
          { class: `day-pill ${d === pickedDate ? 'active' : ''} ${has ? 'has' : 'off'} ${d === today ? 'today' : ''}`, type: 'button', role: 'tab', disabled: !has, 'aria-selected': d === pickedDate, 'aria-label': `${dayLabel(d)}${has ? '' : ', нет окон'}`, onclick: () => { pickedDate = d; draw(res); } },
          h('div', { class: 'wd' }, weekdayShort(d)),
          h('div', { class: 'dn' }, dayNumber(d)),
          h('i', { class: 'dot' }),
        ),
      );
    }

    const list = h('div', { class: 'list two' });
    if (!pickedDate) {
      list.replaceChildren(
        emptyState('🕒', 'Подходящих окон нет', 'Попробуйте убрать часть услуг, выбрать другого специалиста или загляните позже.'),
      );
      list.className = '';
    } else {
      list.append(h('h2', { style: { gridColumn: '1 / -1' } }, longDayLabel(pickedDate)));
      for (const offer of byDate.get(pickedDate)) list.append(offerCard(offer, () => load()));
    }
    body.replaceChildren(summary, who, strip, list);
    requestAnimationFrame(() => {
      const active = strip.querySelector('.day-pill.active');
      if (active) active.scrollIntoView({ inline: 'center', block: 'nearest' });
    });
  }

  await load();
  return root;
}

function offerCard(offer, refresh) {
  return h(
    'article',
    { class: 'card offer' },
    h('div', { class: 'row between' }, h('div', { class: 'time' }, `${offer.start} – ${offer.end}`), h('span', { class: 'chip ok' }, icon('check'), 'Уместится')),
    h('div', { class: 'who' }, avatar(offer.staff, 'lg'), h('div', { class: 'grow' }, h('h3', null, offer.staff.name), offer.staff.specialization ? h('div', { class: 'small muted' }, offer.staff.specialization) : null, h('div', { class: 'tiny muted' }, `Свободно ${offer.window_start || offer.cell_start}–${offer.window_end || offer.cell_end}`))),
    h('div', null, offer.services.map((s) => h('div', { class: 'svc-line' }, h('span', null, `${s.name} · ${duration(s.duration_minutes)}`), h('span', { class: 'num' }, money(s.price_cents))))),
    offer.price_adjust_cents ? h('div', { class: 'svc-line small' }, h('span', null, 'Доплата за окно'), h('span', { class: 'num' }, signedMoney(offer.price_adjust_cents))) : null,
    offer.description || offer.title ? h('p', { class: 'small muted' }, [offer.title, offer.description].filter(Boolean).join(' · ')) : null,
    h('div', { class: 'total' }, h('div', null, h('div', { class: 'tiny muted' }, `Итого · ${duration(offer.total_minutes)}`), h('b', null, money(offer.total_price_cents))), h('button', { class: 'btn primary', type: 'button', onclick: () => openConfirm(offer, refresh) }, 'Записаться')),
  );
}

// ---------------- step 3: confirm ----------------
function openConfirm(offer, refresh) {
  openSheet({
    title: 'Подтверждение записи',
    build: (sheet) => renderConfirm(sheet, offer, refresh),
  });
}

function summaryBlock(offer) {
  return h(
    'div',
    { class: 'card summary' },
    h('div', { class: 'row' }, avatar(offer.staff), h('div', { class: 'grow' }, h('b', null, offer.staff.name), h('div', { class: 'small muted' }, `${longDayLabel(offer.date)}, ${offer.start}–${offer.end}`))),
    h('div', { class: 'small' }, offer.services.map((s) => s.name).join(' + ')),
    h('div', { class: 'row between' }, h('span', { class: 'muted small' }, duration(offer.total_minutes)), h('b', null, money(offer.total_price_cents))),
  );
}

function renderConfirm(sheet, offer, refresh) {
  sheet.body.replaceChildren(summaryBlock(offer));
  if (!store.me.authenticated) {
    sheet.body.append(
      h('p', { class: 'muted small' }, 'Чтобы записаться, войдите через Telegram: туда же придут напоминания о визите.'),
      loginPanel({ compact: true, onSuccess: () => renderConfirm(sheet, offer, refresh) }),
    );
    sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Закрыть'));
    return;
  }
  const me = store.me;
  const needsPhone = !me.client || !me.client.phone || me.client.phone.replace(/\D/g, '').length < 10;
  const name = h('input', { class: 'input', type: 'text', maxlength: '120', autocomplete: 'name', value: (me.client && me.client.name) || me.name || '', placeholder: 'Как к вам обращаться' });
  const phone = h('input', { class: 'input', type: 'tel', autocomplete: 'tel', inputmode: 'tel', placeholder: '+7 900 000-00-00', value: (me.client && me.client.phone) || '' });
  const comment = h('textarea', { class: 'textarea', maxlength: '500', placeholder: 'Пожелания к визиту (необязательно)', style: { minHeight: '70px' } });
  const error = h('p', { class: 'small', style: { color: 'var(--bad)' }, role: 'alert' });
  if (needsPhone) sheet.body.append(field('Имя', name), field('Телефон', phone, 'Нужен салону для связи по записи.'));
  sheet.body.append(field('Комментарий', comment), error);

  const confirm = h('button', { class: 'btn primary', type: 'button' }, 'Подтвердить запись');
  confirm.addEventListener('click', () =>
    withBusy(confirm, async () => {
      error.textContent = '';
      if (needsPhone && phone.value.replace(/\D/g, '').length < 10) {
        error.textContent = 'Укажите номер телефона полностью.';
        return;
      }
      try {
        const booking = await api.post('/client/bookings', {
          ...(offer.cell_id ? { cell_id: offer.cell_id } : { staff_member_id: offer.staff_member_id, start_at: offer.start_at }),
          service_ids: offer.services.map((s) => s.id),
          comment: comment.value.trim() || null,
          ...(needsPhone ? { name: name.value.trim() || null, phone: phone.value.trim() } : {}),
        });
        await loadMe();
        selected = new Set();
        saveSel();
        renderSuccess(sheet, booking);
      } catch (e) {
        error.textContent = friendly(e);
        if (e.status === 409) {
          toast(friendly(e), true);
          sheet.close();
          refresh();
        }
      }
    }),
  );
  sheet.setFooter(h('button', { class: 'btn', type: 'button', onclick: () => sheet.close() }, 'Отмена'), confirm);
}

function renderSuccess(sheet, booking) {
  sheet.body.replaceChildren(
    h(
      'div',
      { class: 'success' },
      h('div', { class: 'tick-big' }, icon('check')),
      h('h2', null, 'Вы записаны!'),
      h('p', { class: 'muted' }, `${longDayLabel(booking.date)}, ${booking.start}–${booking.end}`),
      h('p', null, `${booking.staff.name} · ${booking.services.map((s) => s.name).join(' + ')}`),
      h('b', null, money(booking.total_price_cents)),
      h('p', { class: 'small muted' }, 'Подтверждение и напоминания придут в Telegram.'),
    ),
  );
  sheet.setFooter(
    h('button', { class: 'btn', type: 'button', onclick: () => { sheet.close(); location.hash = '#/book'; } }, 'Ещё запись'),
    h('button', { class: 'btn primary', type: 'button', onclick: () => { sheet.close(); location.hash = '#/mine'; } }, 'Мои записи'),
  );
}
