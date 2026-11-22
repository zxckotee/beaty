import { api, friendly } from '../api.js';
import { navigate } from '../main.js';
import { isManager, store } from '../store.js';
import { field, openSheet, spinner, toast, withBusy } from '../ui.js';
import { h, hueFor, icon, initials } from '../util.js';

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

  async function load() {
    data = await api.get(edit ? '/manager/landing' : '/landing');
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

  function editDgisSheet() {
    openSheet({
      title: 'Как нас найти',
      build: (sheet) => {
        const url = h('input', { class: 'input', value: data.dgis_url || '', placeholder: 'Ссылка на салон в 2ГИС' });
        const parseBtn = h('button', { class: 'btn sm', type: 'button' }, 'Разобрать ссылку');
        parseBtn.addEventListener('click', async () => {
          try {
            const parsed = await api.post('/manager/landing/dgis/parse', { url: url.value.trim() });
            if (parsed.dgis_url) url.value = parsed.dgis_url;
            toast('Ссылка разобрана — сохраните');
          } catch (e) {
            toast(friendly(e), true);
          }
        });
        sheet.body.append(field('Ссылка 2ГИС', h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, url, parseBtn)));
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            try {
              await patchLanding({ dgis_url: url.value.trim() || null });
              sheet.close();
              toast('Адрес сохранён');
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
        sheet.body.append(field('Название', t), field('Описание', d));
        if (item) {
          const photoBtn = h('button', { class: 'btn sm', type: 'button' }, icon('camera'), 'Добавить фото');
          photoBtn.addEventListener('click', () =>
            pickImage(async (f) => {
              try {
                await api.upload(`/manager/landing/portfolio/${item.id}/photos`, f);
                toast('Фото добавлено');
                await load();
                draw();
              } catch (e) {
                toast(friendly(e), true);
              }
            }),
          );
          sheet.body.append(photoBtn);
        }
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            const bodyPayload = {
              title: t.value.trim(),
              description: d.value.trim() || null,
              sort_order: item ? item.sort_order : 0,
            };
            if (item) await api.patch(`/manager/landing/portfolio/${item.id}`, bodyPayload);
            else await api.post('/manager/landing/portfolio', bodyPayload);
            sheet.close();
            await load();
            draw();
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
        sheet.body.append(field('Заголовок', t), field('Текст', b), h('label', { class: 'row' }, vis, 'Показывать на профиле'));
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            const bodyPayload = {
              title: t.value.trim() || null,
              body: b.value,
              is_visible: vis.checked,
              sort_order: post ? post.sort_order : 0,
            };
            if (post) await api.patch(`/manager/landing/posts/${post.id}`, bodyPayload);
            else await api.post('/manager/landing/posts', bodyPayload);
            sheet.close();
            await load();
            draw();
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

  async function mountMap() {
    if (data.map_lat == null || data.map_lon == null || !mapEl) return;
    try {
      await ensureLeaflet();
    } catch {
      return;
    }
    destroyMap();
    map = window.L.map(mapEl, { scrollWheelZoom: false }).setView([data.map_lat, data.map_lon], data.map_zoom || 16);
    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 19,
    }).addTo(map);
    window.L.marker([data.map_lat, data.map_lon]).addTo(map);
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

    const cta = h('button', { class: 'btn profile-cta', type: 'button', onclick: () => navigate('book') }, icon('scissors'), 'Записаться');
    const heroBody = h('div', { class: 'profile-hero-body' }, avatar, titleEl, tagEl, cta);
    const heroSection = h('div', { class: 'profile-hero' }, cover, heroBody);

    const sections = [];

    if (edit) {
      sections.push(
        h('div', { class: 'profile-edit-bar card' }, h('span', { class: 'tiny' }, 'Режим редактирования'), h('a', { class: 'btn sm ghost', href: '#/day' }, 'Расписание')),
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

    const hasMap = data.map_lat != null && data.map_lon != null;
    const showMap = edit || hasMap || data.dgis_url;
    if (showMap) {
      const mapBlock = h('section', { class: 'profile-section' }, h('h2', null, 'Как нас найти'));
      if (hasMap) {
        mapEl = h('div', { id: 'profile-map', class: 'profile-map' });
        mapBlock.append(h('div', { class: 'profile-map-wrap' }, mapEl));
      } else if (edit) {
        mapBlock.append(
          h('button', { class: 'profile-placeholder card', type: 'button', onclick: () => editDgisSheet() }, 'Укажите ссылку 2ГИС'),
        );
      }
      const actions = h('div', { class: 'profile-map-actions' });
      if (data.dgis_url) {
        actions.append(h('a', { class: 'btn sm', href: data.dgis_url, target: '_blank', rel: 'noopener' }, 'Открыть в 2ГИС'));
      }
      if (edit) {
        actions.append(h('button', { class: 'btn sm ghost', type: 'button', onclick: () => editDgisSheet() }, 'Изменить адрес'));
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

    body.replaceChildren(heroSection, ...sections);
    if (hasMap) mountMap();
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