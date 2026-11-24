import { api, friendly } from '../api.js';
import { navigate } from '../main.js';
import { isManager, store } from '../store.js';
import { field, openSheet, photoPicker, spinner, toast, withBusy } from '../ui.js';
import { openWidgetEditor } from '../profile-widget-editor.js?v=23';
import { renderProfileWidget } from '../profile-widgets.js?v=17';
import { h, hueFor, icon, initials, syncHeaderBrand } from '../util.js';

let leafletPromise = null;

function ensureLeaflet() {
  if (window.L) return Promise.resolve();
  if (leafletPromise) return leafletPromise;
  leafletPromise = new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(link);
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('leaflet'));
    document.head.appendChild(script);
  });
  return leafletPromise;
}

function pickImage(onPick) {
  const inp = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/gif', class: 'sr' });
  inp.addEventListener('change', () => {
    const f = inp.files && inp.files[0];
    if (f) onPick(f);
  });
  inp.click();
}

function sectionEmpty(list) {
  return !list || list.length === 0;
}

export async function homeView() {
  const edit = isManager();
  const root = h('div', { class: edit ? 'profile profile--edit' : 'profile' });
  const body = h('div', { class: 'profile-inner' });
  root.append(body);
  body.append(spinner());

  let data = null;
  let map = null;
  let mapEl = null;

  const displayName = () => (data && data.title) || (store.info && store.info.name) || '';

  async function reloadLanding() {
    data = await api.get(edit ? '/manager/landing' : '/landing');
    draw();
  }

  async function load() {
    data = await api.get(edit ? '/manager/landing' : '/landing');
    if (store.info && data.avatar_url) {
      store.info.avatar_url = data.avatar_url;
      syncHeaderBrand(store.info);
    }
  }

  function destroyMap() {
    if (map) {
      map.remove();
      map = null;
    }
  }

  async function patchLanding(payload) {
    const next = await api.patch('/manager/landing', payload);
    Object.assign(data, next);
    draw();
  }

  function dgisLocationsList(d) {
    const raw = (d && d.dgis_locations) || [];
    if (raw.length) {
      return raw.map((loc) => ({
        dgis_url: loc.dgis_url || '',
        label: loc.label || '',
      }));
    }
    if (d && d.dgis_url) {
      return [{ dgis_url: d.dgis_url, label: '' }];
    }
    return [{ dgis_url: '', label: '' }];
  }

  function embedMapNode(d) {
    const wrap = h('div', { class: 'profile-dgis-embed' });
    const src = d && d.dgis_embed_src;
    if (src) {
      wrap.append(
        h('iframe', {
          src,
          title: 'Карта 2ГИС',
          loading: 'lazy',
          referrerpolicy: 'no-referrer-when-downgrade',
          style: { border: 0, width: '100%', height: '100%' },
        }),
      );
    } else if (d && d.dgis_embed_html && String(d.dgis_embed_html).trim()) {
      wrap.insertAdjacentHTML('beforeend', d.dgis_embed_html);
    }
    return wrap;
  }

  async function saveDgisLocations(locations) {
    const payload = locations
      .map((row) => ({
        dgis_url: (row.dgis_url || '').trim(),
        label: (row.label || '').trim() || null,
      }))
      .filter((row) => row.dgis_url);
    await patchLanding({ dgis_locations: payload });
    toast('Сохранено');
    await load();
    draw();
  }

  function buildLocationRows(initial) {
    const rows = h('div', { class: 'col profile-dgis-locations', style: { gap: '10px' } });
    const editors = [];

    function addRow(url = '', label = '') {
      const urlInp = h('input', {
        class: 'input',
        value: url,
        placeholder: 'https://2gis.ru/…/firm/…',
      });
      const labelInp = h('input', {
        class: 'input',
        value: label,
        placeholder: 'Подпись (необязательно)',
      });
      const removeBtn = h('button', {
        class: 'btn sm ghost',
        type: 'button',
        title: 'Удалить',
      }, '×');
      const row = h(
        'div',
        { class: 'col', style: { gap: '6px' } },
        urlInp,
        labelInp,
        removeBtn,
      );
      removeBtn.addEventListener('click', () => {
        if (editors.length <= 1) {
          urlInp.value = '';
          labelInp.value = '';
          return;
        }
        row.remove();
        const i = editors.indexOf(entry);
        if (i >= 0) editors.splice(i, 1);
      });
      const entry = { urlInp, labelInp, row };
      editors.push(entry);
      rows.append(row);
    }

    for (const loc of initial) addRow(loc.dgis_url, loc.label);
    if (!editors.length) addRow();

    return { rows, editors, addRow, values: () => editors.map((e) => ({ dgis_url: e.urlInp.value, label: e.labelInp.value })) };
  }

  function buildInlineMapEditor() {
    const locEditor = buildLocationRows(dgisLocationsList(data));
    const addBtn = h('button', { class: 'btn sm ghost', type: 'button' }, icon('plus'), 'Добавить филиал');
    addBtn.addEventListener('click', () => locEditor.addRow());
    const saveBtn = h('button', { class: 'btn sm primary', type: 'button' }, 'Сохранить адреса');
    saveBtn.addEventListener('click', () =>
      withBusy(saveBtn, async () => {
        try {
          await saveDgisLocations(locEditor.values());
        } catch (e) {
          toast(friendly(e), true);
        }
      }),
    );
    const clearBtn =
      hasDgisMap(data) &&
      h('button', { class: 'btn sm ghost', type: 'button' }, 'Очистить → OpenStreetMap');
    if (clearBtn) {
      clearBtn.addEventListener('click', () =>
        withBusy(clearBtn, async () => {
          try {
            await saveDgisLocations([]);
          } catch (e) {
            toast(friendly(e), true);
          }
        }),
      );
    }
    return h(
      'div',
      { class: 'profile-map-editor card' },
      h('h3', { class: 'profile-map-editor-title' }, 'Адреса на карте 2ГИС'),
      h(
        'p',
        { class: 'tiny muted' },
        'Вставьте ссылки на филиалы в 2ГИС — на профиле появится одна карта со всеми точками. API-ключ не нужен.',
      ),
      locEditor.rows,
      h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, addBtn, saveBtn, clearBtn),
    );
  }

  function hasDgisMap(d) {
    if (!d) return false;
    if (d.dgis_embed_src) return true;
    if (d.dgis_locations && d.dgis_locations.length) return true;
    return Boolean(d.dgis_embed_html && String(d.dgis_embed_html).trim());
  }

  function editDgisSheet() {
    openSheet({
      title: 'Адреса 2ГИС',
      build: (sheet) => {
        const locEditor = buildLocationRows(dgisLocationsList(data));
        const addBtn = h('button', { class: 'btn sm ghost', type: 'button' }, icon('plus'), 'Филиал');
        addBtn.addEventListener('click', () => locEditor.addRow());
        sheet.body.append(
          h('p', { class: 'tiny muted' }, 'Ссылка на карточку организации в 2ГИС (с /firm/ и номером).'),
          locEditor.rows,
          addBtn,
        );
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            try {
              await saveDgisLocations(locEditor.values());
              sheet.close();
            } catch (e) {
              toast(friendly(e), true);
            }
          }),
        );
        sheet.setFooter(save);
      },
    });
  }

  function editPortfolio(item) {
    openSheet({
      title: item ? 'Работа' : 'Новая работа',
      build: (sheet) => {
        const t = h('input', { class: 'input', value: item ? item.title : '', placeholder: 'Название' });
        const d = h('textarea', { class: 'textarea' }, item ? item.description || '' : '');
        const firstPhoto = item && item.photo_urls && item.photo_urls[0];
        const photos = photoPicker({ url: firstPhoto, name: item ? item.title : 'Работа', square: true });
        sheet.body.append(
          field('Фото', photos.el),
          field('Название', t),
          field('Описание', d),
        );
        if (item && item.photo_urls && item.photo_urls.length > 1) {
          sheet.body.append(
            h('p', { class: 'tiny muted' }, `Всего фото: ${item.photo_urls.length}. Здесь меняется обложка карточки.`),
          );
        }
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            const title = t.value.trim();
            if (!title) {
              toast('Укажите название', true);
              return;
            }
            const file = photos.getFile();
            if (!item && !file && !firstPhoto) {
              toast('Добавьте фото работы', true);
              return;
            }
            const bodyPayload = {
              title,
              description: d.value.trim() || null,
              sort_order: item ? item.sort_order : 0,
            };
            try {
              let itemId = item ? item.id : null;
              if (item) await api.patch(`/manager/landing/portfolio/${item.id}`, bodyPayload);
              else {
                const created = await api.post('/manager/landing/portfolio', bodyPayload);
                itemId = created.id;
              }
              if (file && itemId) {
                const uploaded = await api.upload(`/manager/landing/portfolio/${itemId}/photos`, file);
                const urls = uploaded.photo_urls || [];
                if (item && urls.length > 1) {
                  const last = urls[urls.length - 1];
                  await api.patch(`/manager/landing/portfolio/${itemId}`, {
                    photo_urls: [last, ...urls.slice(0, -1)],
                  });
                }
              }
              sheet.close();
              await load();
              draw();
              toast(item ? 'Работа сохранена' : 'Работа добавлена');
            } catch (e) {
              toast(friendly(e), true);
            }
          }),
        );
        sheet.setFooter(save);
      },
    });
  }

  async function removePortfolio(id) {
    await api.del(`/manager/landing/portfolio/${id}`);
    await load();
    draw();
  }

  function editPost(post) {
    openSheet({
      title: post ? 'Пост' : 'Новый пост',
      build: (sheet) => {
        const t = h('input', { class: 'input', value: post ? post.title || '' : '', placeholder: 'Заголовок' });
        const b = h('textarea', { class: 'textarea' }, post ? post.body || '' : '');
        const vis = h('input', { class: 'check', type: 'checkbox', checked: post ? post.is_visible !== false : true });
        const firstPhoto = post && post.photo_urls && post.photo_urls[0];
        const photos = photoPicker({ url: firstPhoto, name: post?.title || 'Пост', square: true });
        sheet.body.append(
          field('Фото', photos.el),
          h('p', { class: 'tiny muted' }, 'Необязательно. Можно добавить при создании или позже.'),
          field('Заголовок', t),
          field('Текст', b),
          h('label', { class: 'row' }, vis, 'Показывать на профиле'),
        );
        if (post && post.photo_urls && post.photo_urls.length > 0) {
          const addPhoto = h('button', { class: 'btn sm', type: 'button' }, icon('camera'), 'Добавить ещё фото');
          addPhoto.addEventListener('click', () =>
            pickImage(async (f) => {
              try {
                await api.upload(`/manager/landing/posts/${post.id}/photos`, f);
                toast('Фото добавлено');
                await load();
                draw();
                sheet.close();
              } catch (e) {
                toast(friendly(e), true);
              }
            }),
          );
          if (post.photo_urls.length > 1) {
            sheet.body.append(h('p', { class: 'tiny muted' }, `В посте ${post.photo_urls.length} фото.`));
          }
          sheet.body.append(addPhoto);
        }
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            const bodyPayload = {
              title: t.value.trim() || null,
              body: b.value,
              is_visible: vis.checked,
              sort_order: post ? post.sort_order : 0,
            };
            try {
              let postId = post ? post.id : null;
              if (post) await api.patch(`/manager/landing/posts/${post.id}`, bodyPayload);
              else {
                const created = await api.post('/manager/landing/posts', bodyPayload);
                postId = created.id;
              }
              const file = photos.getFile();
              if (file && postId) await api.upload(`/manager/landing/posts/${postId}/photos`, file);
              sheet.close();
              await load();
              draw();
              toast(post ? 'Пост сохранён' : 'Пост добавлен');
            } catch (e) {
              toast(friendly(e), true);
            }
          }),
        );
        sheet.setFooter(save);
      },
    });
  }

  async function removePost(id) {
    await api.del(`/manager/landing/posts/${id}`);
    await load();
    draw();
  }

  function bindEditable(el, fieldName, placeholder) {
    el.addEventListener('focus', () => {
      if (el.classList.contains('profile-ph')) {
        el.textContent = '';
        el.classList.remove('profile-ph');
      }
    });
    el.addEventListener('blur', async () => {
      const text = el.textContent.trim();
      if (!text) {
        el.textContent = placeholder;
        el.classList.add('profile-ph');
      }
      const current = (data[fieldName] || '').trim();
      if (text === current) return;
      try {
        await patchLanding({ [fieldName]: text || null });
      } catch (e) {
        toast(friendly(e), true);
        draw();
      }
    });
  }

  function mapPointsFromData(d) {
    const pts = [];
    for (const loc of d.dgis_locations || []) {
      if (loc.map_lat != null && loc.map_lon != null) {
        pts.push({ lat: Number(loc.map_lat), lon: Number(loc.map_lon), label: loc.label || '' });
      }
    }
    if (!pts.length && d.map_lat != null && d.map_lon != null) {
      pts.push({ lat: Number(d.map_lat), lon: Number(d.map_lon), label: d.title || '' });
    }
    return pts;
  }

  async function mountMap() {
    const pts = mapPointsFromData(data);
    if (!pts.length || !mapEl) return;
    try {
      await ensureLeaflet();
    } catch {
      return;
    }
    destroyMap();
    const zoom = data.map_zoom || 16;
    map = window.L.map(mapEl, { scrollWheelZoom: false, attributionControl: true });
    if (map.attributionControl) map.attributionControl.setPrefix('');
    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    const markers = [];
    for (const p of pts) {
      const m = window.L.marker([p.lat, p.lon]).addTo(map);
      if (p.label) m.bindPopup(p.label);
      markers.push(m);
    }
    if (pts.length === 1) {
      map.setView([pts[0].lat, pts[0].lon], zoom);
    } else {
      const group = window.L.featureGroup(markers);
      map.fitBounds(group.getBounds().pad(0.12));
    }
    setTimeout(() => map.invalidateSize(), 80);
  }

  function draw() {
    if (!data) return;
    destroyMap();
    const name = displayName();
    const hue = hueFor(name);
    const coverStyle = data.cover_url
      ? { backgroundImage: `url(${data.cover_url})` }
      : { background: `linear-gradient(135deg, hsl(${hue} 58% 48%), hsl(${(hue + 40) % 360} 55% 42%))` };

    const cover = h('div', { class: 'profile-cover', style: coverStyle });
    if (edit) {
      cover.classList.add('profile-cover--edit');
      cover.append(h('span', { class: 'profile-edit-hint' }, icon('camera'), 'Изменить обложку'));
      cover.addEventListener('click', () =>
        pickImage(async (f) => {
          try {
            const r = await api.upload('/manager/landing/photo/cover', f);
            data.cover_url = r.cover_url;
            draw();
            toast('Обложка обновлена');
          } catch (e) {
            toast(friendly(e), true);
          }
        }),
      );
    }

    let avatar;
    if (data.avatar_url) {
      avatar = h('img', { class: 'profile-avatar', src: data.avatar_url, alt: '' });
    } else {
      avatar = h('div', {
        class: 'profile-avatar profile-avatar-fallback',
        style: { background: `linear-gradient(135deg, hsl(${hue} 58% 48%), hsl(${(hue + 24) % 360} 52% 40%))` },
      }, initials(name));
    }
    if (edit) {
      avatar.classList.add('profile-avatar--edit');
      avatar.title = 'Изменить фото';
      avatar.addEventListener('click', (ev) => {
        ev.stopPropagation();
        pickImage(async (f) => {
          try {
            const r = await api.upload('/manager/landing/photo/avatar', f);
            data.avatar_url = r.avatar_url;
            if (store.info) {
              store.info.avatar_url = r.avatar_url;
              syncHeaderBrand(store.info);
            }
            draw();
            toast('Аватар обновлён');
          } catch (e) {
            toast(friendly(e), true);
          }
        });
      });
    }

    const titleText = (data.title || '').trim();
    const tagText = (data.tagline || '').trim();
    const titleEl = h(
      edit ? 'h1' : 'h1',
      {
        class: `profile-title${edit ? ' profile-title--edit' : ''}${!titleText && !edit ? ' profile-ph' : ''}`,
        contenteditable: edit ? 'true' : 'false',
        spellcheck: 'true',
      },
      titleText || (edit ? '' : 'Название салона'),
    );
    const tagEl = h(
      'p',
      {
        class: `profile-tagline${edit ? ' profile-tagline--edit' : ''}${!tagText && !edit ? ' profile-ph' : ''}`,
        contenteditable: edit ? 'true' : 'false',
      },
      tagText || (edit ? '' : 'Краткий девиз салона'),
    );
    if (edit) {
      if (!titleText) {
        titleEl.textContent = '';
        titleEl.dataset.ph = 'Добавьте название';
        titleEl.classList.add('profile-ph');
      }
      if (!tagText) {
        tagEl.textContent = '';
        tagEl.dataset.ph = 'Краткий девиз салона';
        tagEl.classList.add('profile-ph');
      }
      bindEditable(titleEl, 'title', 'Добавьте название');
      bindEditable(tagEl, 'tagline', 'Краткий девиз салона');
    }

    const heroBody = h('div', { class: 'profile-hero-body' }, avatar, titleEl, tagEl);

    const sections = [];

    function sortedWidgets() {
      return (data.widgets || []).slice().sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    }

    async function moveWidget(widget, delta) {
      const list = sortedWidgets();
      const i = list.findIndex((w) => w.id === widget.id);
      const j = i + delta;
      if (i < 0 || j < 0 || j >= list.length) return;
      const next = list.slice();
      [next[i], next[j]] = [next[j], next[i]];
      const items = next.map((w, idx) => ({ id: w.id, sort_order: idx }));
      try {
        await api.put('/manager/landing/widgets/reorder', { items });
        await reloadLanding();
      } catch (e) {
        toast(friendly(e), true);
      }
    }

    async function removeWidget(widget) {
      try {
        await api.del(`/manager/landing/widgets/${widget.id}`);
        toast('Виджет удалён');
        await reloadLanding();
      } catch (e) {
        toast(friendly(e), true);
      }
    }

    async function duplicateWidget(widget) {
      try {
        await api.post('/manager/landing/widgets', {
          template: widget.template,
          payload: widget.payload,
          sort_order: sortedWidgets().length,
        });
        toast('Копия создана');
        await reloadLanding();
      } catch (e) {
        toast(friendly(e), true);
      }
    }

    async function toggleWidgetVisible(widget) {
      try {
        await api.patch(`/manager/landing/widgets/${widget.id}`, { is_visible: !widget.is_visible });
        await reloadLanding();
      } catch (e) {
        toast(friendly(e), true);
      }
    }

    function buildWidgetsZone() {
      const widgets = sortedWidgets();
      const visibleToGuest = widgets.filter((w) => w.is_visible);
      if (!edit && !visibleToGuest.length) return null;

      const zone = h('div', { class: 'profile-widgets-zone' });
      for (const w of widgets) {
        if (!edit && !w.is_visible) continue;
        const wrap = h('div', { class: 'profile-widget-wrap' });
        wrap.append(renderProfileWidget(w, { mode: 'app', onBook: () => navigate('book') }));
        if (edit) {
          wrap.append(
            h('div', { class: 'profile-card-actions row' },
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => openWidgetEditor(w, { onSaved: reloadLanding }) }, 'Изменить'),
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => duplicateWidget(w) }, 'Дублировать'),
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => moveWidget(w, -1) }, '↑'),
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => moveWidget(w, 1) }, '↓'),
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => toggleWidgetVisible(w) }, w.is_visible ? 'Скрыть' : 'Показать'),
              h('button', { class: 'btn sm danger', type: 'button', onclick: () => removeWidget(w) }, 'Удалить'),
            ),
          );
        }
        zone.append(wrap);
      }
      if (edit) {
        const count = widgets.filter((w) => w.is_visible).length;
        zone.append(
          h('button', {
            class: 'btn ghost profile-add-widget',
            type: 'button',
            onclick: () => openWidgetEditor(null, { sortOrder: widgets.length, onSaved: reloadLanding }),
          }, icon('plus'), 'Добавить виджет'),
          h('p', { class: 'tiny muted', style: { textAlign: 'center' } }, `${count} блоков на профиле`),
        );
      }
      return zone;
    }

    const widgetsZone = buildWidgetsZone();

    if (edit) {
      sections.push(
        h('div', { class: 'profile-edit-bar card' }, h('span', { class: 'tiny' }, 'Режим редактирования'), h('a', { class: 'btn sm ghost', href: '#/schedule' }, 'Расписание')),
      );
    }

    const showPortfolio = edit || !sectionEmpty(data.portfolio);
    if (showPortfolio) {
      const grid = h('div', { class: 'profile-portfolio-grid' });
      for (const item of data.portfolio || []) {
        const img = item.photo_urls && item.photo_urls[0] ? h('img', { src: item.photo_urls[0], alt: '' }) : h('div', { class: 'profile-portfolio-empty' }, icon('camera'));
        const card = h('div', { class: 'profile-portfolio-card' }, img, h('div', { class: 'body' }, h('h3', null, item.title), item.description ? h('p', null, item.description) : null));
        if (edit) {
          card.classList.add('profile-portfolio-card--edit');
          card.append(
            h('div', { class: 'profile-card-actions row' },
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => editPortfolio(item) }, 'Изменить'),
              h('button', { class: 'btn sm danger', type: 'button', onclick: () => removePortfolio(item.id) }, 'Удалить'),
            ),
          );
        }
        grid.append(card);
      }
      if (edit) {
        grid.append(
          h('button', { class: 'profile-add-tile', type: 'button', onclick: () => editPortfolio(null) }, icon('plus'), 'Добавить работу'),
        );
      } else if (sectionEmpty(data.portfolio)) {
        grid.append(h('p', { class: 'muted tiny' }, 'Скоро здесь появятся работы'));
      }
      sections.push(h('section', { class: 'profile-section' }, h('h2', null, 'Портфолио'), grid));
    }

    const hasEmbed = hasDgisMap(data);
    const hasMap = mapPointsFromData(data).length > 0;
    const showMap = edit || hasEmbed || hasMap || data.dgis_url;
    if (showMap) {
      const mapBlock = h('section', { class: 'profile-section' }, h('h2', null, 'Как нас найти'));
      if (hasEmbed) {
        mapBlock.append(embedMapNode(data));
      } else if (hasMap) {
        mapEl = h('div', { id: 'profile-map', class: 'profile-map' });
        mapBlock.append(h('div', { class: 'profile-map-wrap' }, mapEl));
        if (edit) {
          mapBlock.append(h('p', { class: 'tiny muted profile-map-hint' }, 'Сейчас показана OpenStreetMap. Добавьте ссылки 2ГИС ниже, чтобы показать карту 2ГИС.'));
        }
      } else if (edit) {
        mapBlock.append(
          h('button', { class: 'profile-placeholder card', type: 'button', onclick: () => editDgisSheet() }, 'Добавьте ссылки на филиалы в 2ГИС'),
        );
      }
      if (edit) mapBlock.append(buildInlineMapEditor());
      const actions = h('div', { class: 'profile-map-actions' });
      const locs = (data.dgis_locations && data.dgis_locations.length) ? data.dgis_locations : (data.dgis_url ? [{ dgis_url: data.dgis_url }] : []);
      for (const loc of locs) {
        if (loc.dgis_url) {
          actions.append(
            h('a', {
              class: 'btn sm',
              href: loc.dgis_url,
              target: '_blank',
              rel: 'noopener',
            }, loc.label || 'Открыть в 2ГИС'),
          );
        }
      }
      if (edit) {
        actions.append(h('button', { class: 'btn sm ghost', type: 'button', onclick: () => editDgisSheet() }, 'Ссылка 2ГИС'));
      }
      if (actions.childNodes.length) mapBlock.append(actions);
      sections.push(mapBlock);
    }

    const showPosts = edit || !sectionEmpty(data.posts);
    if (showPosts) {
      const list = h('div', { class: 'profile-posts' });
      for (const post of data.posts || []) {
        const card = h('article', { class: 'profile-post-card' }, post.title ? h('h3', null, post.title) : null, h('div', { class: 'profile-post-body' }, post.body || ''));
        if (post.photo_urls && post.photo_urls.length) {
          const photos = h('div', { class: 'profile-post-photos' });
          for (const url of post.photo_urls) photos.append(h('img', { src: url, alt: '' }));
          card.append(photos);
        }
        if (edit) {
          card.append(
            h('div', { class: 'profile-card-actions row' },
              h('button', { class: 'btn sm ghost', type: 'button', onclick: () => editPost(post) }, 'Изменить'),
              h('button', { class: 'btn sm danger', type: 'button', onclick: () => removePost(post.id) }, 'Удалить'),
            ),
          );
        }
        list.append(card);
      }
      if (edit) {
        list.append(h('button', { class: 'profile-add-tile', type: 'button', onclick: () => editPost(null) }, icon('plus'), 'Добавить пост'));
      }
      sections.push(h('section', { class: 'profile-section' }, h('h2', null, 'Новости'), list));
    }

    root.replaceChildren(cover, body);
    body.replaceChildren(heroBody, widgetsZone, ...sections.filter(Boolean));
    if (!hasEmbed && hasMap) mountMap();
  }

  try {
    await load();
    draw();
  } catch (e) {
    body.replaceChildren(h('div', { class: 'empty card' }, h('p', null, friendly(e))));
  }

  root.cleanup = () => destroyMap();
  return root;
}