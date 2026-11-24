import { api, friendly, tenantId } from '../api.js';
import { h, icon } from '../util.js';
import { field, openSheet, photoPicker, spinner, toast, withBusy } from '../ui.js';

export async function landingView() {
  const root = h('div');
  let data = null;
  const panel = h('div');
  root.append(
    h(
      'div',
      { class: 'page-head' },
      h('div', null, h('h1', null, 'Лендинг'), h('p', { class: 'muted' }, 'Публичная страница студии и карта.')),
      h('div', { class: 'row' }, h('button', { class: 'btn sm', type: 'button', onclick: () => openStudio() }, 'Открыть studio'), h('button', { class: 'btn primary', type: 'button', id: 'land-save' }, 'Сохранить')),
    ),
    panel,
  );
  panel.append(spinner());

  function openStudio() {
    const id = tenantId;
    window.open(`/t/${id}/studio`, '_blank');
  }

  async function reload() {
    data = await api.get('/manager/landing');
    draw();
  }

  function draw() {
    if (!data) return;
    const published = h('input', { class: 'check', type: 'checkbox', checked: data.is_published, id: 'land-pub' });
    const title = h('input', { class: 'input', value: data.title || '', placeholder: 'Название на лендинге' });
    const tagline = h('textarea', { class: 'textarea', placeholder: 'Девиз (курсив)' }, data.tagline || '');
    const cover = photoPicker({ url: data.cover_url, name: data.title || 'Cover', square: true });
    const avatar = photoPicker({ url: data.avatar_url, name: data.title || 'A', square: false });
    const dgisRows = h('div', { class: 'col', style: { gap: '8px' } });
    const locs = (data.dgis_locations && data.dgis_locations.length)
      ? data.dgis_locations
      : data.dgis_url
        ? [{ dgis_url: data.dgis_url, label: '' }]
        : [{ dgis_url: '', label: '' }];
    const locInputs = [];
    for (const loc of locs) {
      const inp = h('input', { class: 'input', value: loc.dgis_url || '', placeholder: 'Ссылка 2ГИС на филиал' });
      locInputs.push(inp);
      dgisRows.append(inp);
    }
    const complex = h('input', { class: 'input', value: data.dgis_complex_id || '', placeholder: 'complex_id (ТЦ, опционально)' });
    const lon = h('input', { class: 'input', type: 'number', step: 'any', value: data.map_lon ?? '', placeholder: 'Долгота' });
    const lat = h('input', { class: 'input', type: 'number', step: 'any', value: data.map_lat ?? '', placeholder: 'Широта' });
    const zoom = h('input', { class: 'input', type: 'number', step: 'any', value: data.map_zoom ?? '', placeholder: 'Zoom' });
    const parseBtn = h('button', { class: 'btn sm', type: 'button' }, 'Разобрать ссылку');

    parseBtn.addEventListener('click', async () => {
      const first = locInputs[0];
      if (!first || !first.value.trim()) return;
      try {
        const parsed = await api.post('/manager/landing/dgis/parse', { url: first.value.trim() });
        if (parsed.map_lon != null) lon.value = parsed.map_lon;
        if (parsed.map_lat != null) lat.value = parsed.map_lat;
        if (parsed.map_zoom != null) zoom.value = parsed.map_zoom;
        if (parsed.dgis_url) first.value = parsed.dgis_url;
        toast('Ссылка разобрана');
      } catch (e) {
        toast(friendly(e), true);
      }
    });

    const portfolioList = h('div', { class: 'col', style: { gap: '10px' } });
    for (const item of data.portfolio || []) {
      portfolioList.append(
        h(
          'div',
          { class: 'card row between' },
          h('span', null, item.title),
          h('div', { class: 'row' },
            h('button', { class: 'btn sm ghost', type: 'button', onclick: () => editPortfolio(item) }, 'Изменить'),
            h('button', { class: 'btn sm danger', type: 'button', onclick: () => removePortfolio(item.id) }, 'Удалить'),
          ),
        ),
      );
    }

    const postsList = h('div', { class: 'col', style: { gap: '10px' } });
    for (const post of data.posts || []) {
      postsList.append(
        h(
          'div',
          { class: 'card row between' },
          h('span', null, post.title || 'Пост'),
          h('div', { class: 'row' },
            h('button', { class: 'btn sm ghost', type: 'button', onclick: () => editPost(post) }, 'Изменить'),
            h('button', { class: 'btn sm danger', type: 'button', onclick: () => removePost(post.id) }, 'Удалить'),
          ),
        ),
      );
    }

    panel.replaceChildren(
      h('label', { class: 'row' }, published, 'Опубликовать лендинг'),
      cover.el,
      avatar.el,
      field('Название', title),
      field('Девиз', tagline),
      field('Ссылки на филиалы 2ГИС', h('div', { class: 'col', style: { gap: '8px' } }, dgisRows, parseBtn)),
      h('div', { class: 'grid2' }, field('Долгота', lon), field('Широта', lat)),
      field('Масштаб карты', zoom),
      field('complex_id (FloorsJS)', complex),
      h('h3', null, 'Портфолио'),
      portfolioList,
      h('button', { class: 'btn sm', type: 'button', onclick: () => editPortfolio(null) }, icon('plus'), 'Добавить работу'),
      h('h3', { style: { marginTop: '20px' } }, 'Посты'),
      postsList,
      h('button', { class: 'btn sm', type: 'button', onclick: () => editPost(null) }, icon('plus'), 'Добавить пост'),
    );

    const saveBtn = root.querySelector('#land-save');
    saveBtn.onclick = () =>
      withBusy(saveBtn, async () => {
        try {
          const payload = {
            title: title.value.trim() || null,
            tagline: tagline.value.trim() || null,
            dgis_locations: locInputs
              .map((inp) => ({ dgis_url: inp.value.trim() }))
              .filter((row) => row.dgis_url),
            dgis_complex_id: complex.value.trim() || null,
            map_lon: lon.value === '' ? null : Number(lon.value),
            map_lat: lat.value === '' ? null : Number(lat.value),
            map_zoom: zoom.value === '' ? null : Number(zoom.value),
            is_published: published.checked,
          };
          data = await api.patch('/manager/landing', payload);
          const cf = cover.getFile();
          if (cf) await api.upload('/manager/landing/photo/cover', cf);
          const af = avatar.getFile();
          if (af) await api.upload('/manager/landing/photo/avatar', af);
          toast('Лендинг сохранён');
          await reload();
        } catch (e) {
          toast(friendly(e), true);
        }
      });
  }

  function editPortfolio(item) {
    openSheet({
      title: item ? 'Работа' : 'Новая работа',
      build: (sheet) => {
        const t = h('input', { class: 'input', value: item ? item.title : '', placeholder: 'Название' });
        const d = h('textarea', { class: 'textarea' }, item ? item.description || '' : '');
        sheet.body.append(field('Название', t), field('Описание', d));
        let photoBtn = null;
        if (item) {
          photoBtn = h('button', { class: 'btn sm', type: 'button' }, 'Добавить фото');
          photoBtn.addEventListener('click', () => {
            const inp = h('input', { type: 'file', accept: 'image/*' });
            inp.addEventListener('change', async () => {
              const f = inp.files && inp.files[0];
              if (!f) return;
              try {
                await api.upload(`/manager/landing/portfolio/${item.id}/photos`, f);
                toast('Фото добавлено');
              } catch (e) {
                toast(friendly(e), true);
              }
            });
            inp.click();
          });
          sheet.body.append(photoBtn);
        }
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            const body = { title: t.value.trim(), description: d.value.trim() || null, sort_order: item ? item.sort_order : 0 };
            if (item) await api.patch(`/manager/landing/portfolio/${item.id}`, body);
            else await api.post('/manager/landing/portfolio', body);
            sheet.close();
            await reload();
          }),
        );
        sheet.setFooter(save);
      },
    });
  }

  async function removePortfolio(id) {
    await api.del(`/manager/landing/portfolio/${id}`);
    await reload();
  }

  function editPost(post) {
    openSheet({
      title: post ? 'Пост' : 'Новый пост',
      build: (sheet) => {
        const t = h('input', { class: 'input', value: post ? post.title || '' : '', placeholder: 'Заголовок' });
        const b = h('textarea', { class: 'textarea' }, post ? post.body || '' : '');
        const vis = h('input', { class: 'check', type: 'checkbox', checked: post ? post.is_visible !== false : true });
        sheet.body.append(field('Заголовок', t), field('Текст', b), h('label', { class: 'row' }, vis, 'Показывать на лендинге'));
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            const body = {
              title: t.value.trim() || null,
              body: b.value,
              is_visible: vis.checked,
              sort_order: post ? post.sort_order : 0,
            };
            if (post) await api.patch(`/manager/landing/posts/${post.id}`, body);
            else await api.post('/manager/landing/posts', body);
            sheet.close();
            await reload();
          }),
        );
        sheet.setFooter(save);
      },
    });
  }

  async function removePost(id) {
    await api.del(`/manager/landing/posts/${id}`);
    await reload();
  }

  try {
    await reload();
  } catch (e) {
    panel.replaceChildren(h('p', { class: 'err' }, friendly(e)));
  }
  return root;
}