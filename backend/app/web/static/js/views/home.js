import { api, friendly } from '../api.js';
import { navigate } from '../main.js';
import { isManager, store } from '../store.js';
import { field, openSheet, photoPicker, spinner, toast, withBusy } from '../ui.js';
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

  function embedMapNode(html) {
    const wrap = h('div', { class: 'profile-dgis-embed' });
    if (html) wrap.insertAdjacentHTML('beforeend', html);
    return wrap;
  }

  function dgisEmbedField(initialHtml) {
    return h(
      'textarea',
      {
        class: 'textarea profile-embed-input',
        placeholder: '<iframe src="https://..." width="100%" height="400"></iframe>',
      },
      initialHtml ? stripIframeWrapper(initialHtml) : '',
    );
  }

  async function saveDgisFields({ dgis_url, dgis_embed_html }) {
    await patchLanding({
      dgis_url: dgis_url !== undefined ? dgis_url : data.dgis_url || null,
      dgis_embed_html: dgis_embed_html !== undefined ? dgis_embed_html : data.dgis_embed_html || null,
    });
    toast('Сохранено');
    await load();
    draw();
  }

  function buildInlineMapEditor() {
    const embed = dgisEmbedField(data.dgis_embed_html);
    const saveEmbed = h('button', { class: 'btn sm primary', type: 'button' }, 'Сохранить виджет');
    saveEmbed.addEventListener('click', () =>
      withBusy(saveEmbed, async () => {
        try {
          await saveDgisFields({ dgis_embed_html: embed.value.trim() || null });
        } catch (e) {
          toast(friendly(e), true);
        }
      }),
    );
    const clearEmbed =
      hasDgisEmbed(data) &&
      h('button', { class: 'btn sm ghost', type: 'button' }, 'Убрать виджет → OpenStreetMap');
    if (clearEmbed) {
      clearEmbed.addEventListener('click', () =>
        withBusy(clearEmbed, async () => {
          try {
            embed.value = '';
            await saveDgisFields({ dgis_embed_html: null });
          } catch (e) {
            toast(friendly(e), true);
          }
        }),
      );
    }
    const actions = h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, saveEmbed, clearEmbed);
    return h(
      'div',
      { class: 'profile-map-editor card' },
      h('h3', { class: 'profile-map-editor-title' }, 'Виджет карты 2ГИС'),
      h(
        'p',
        { class: 'tiny muted' },
        'Вставьте iframe из конструктора карт 2ГИС — он заменит карту OpenStreetMap на профиле. Ссылку на салон можно указить в «Ссылка 2ГИС».',
      ),
      embed,
      actions,
    );
  }

  function hasDgisEmbed(d) {
    return Boolean(d.dgis_embed_html && String(d.dgis_embed_html).trim());
  }

  function editDgisSheet() {
    openSheet({
      title: 'Ссылка 2ГИС',
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
        const embed = dgisEmbedField(data.dgis_embed_html);
        sheet.body.append(
          h(
            'div',
            { class: 'field' },
            h('label', null, 'Виджет карты 2ГИС (приоритет над OpenStreetMap)'),
            embed,
            h('p', { class: 'tiny muted' }, 'Конструктор карт в личном кабинете 2ГИС → скопируйте код iframe.'),
          ),
          field('Ссылка на салон', h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, url, parseBtn)),
          h('p', { class: 'tiny muted' }, 'Ссылка нужна для кнопки «Открыть в 2ГИС» и запасной OSM-карты, если виджет пустой.'),
        );
        const save = h('button', { class: 'btn primary', type: 'button' }, 'Сохранить');
        save.addEventListener('click', () =>
          withBusy(save, async () => {
            try {
              await saveDgisFields({
                dgis_url: url.value.trim() || null,
                dgis_embed_html: embed.value.trim() || null,
              });
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

  function stripIframeWrapper(sanitizedHtml) {
    const m = sanitizedHtml.match(/<iframe[\s\S]*?<\/iframe>/i);
    return m ? m[0] : sanitizedHtml;
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

  async function mountMap() {
    if (data.map_lat == null || data.map_lon == null || !mapEl) return;
    try {
      await ensureLeaflet();
    } catch {
      return;
    }
    destroyMap();
    map = window.L.map(mapEl, { scrollWheelZoom: false, attributionControl: true }).setView(
      [data.map_lat, data.map_lon],
      data.map_zoom || 16,
    );
    if (map.attributionControl) map.attributionControl.setPrefix('');
    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap</a>',
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

    const hasEmbed = hasDgisEmbed(data);
    const hasMap = data.map_lat != null && data.map_lon != null;
    const showMap = edit || hasEmbed || hasMap || data.dgis_url;
    if (showMap) {
      const mapBlock = h('section', { class: 'profile-section' }, h('h2', null, 'Как нас найти'));
      if (hasEmbed) {
        mapBlock.append(embedMapNode(data.dgis_embed_html));
      } else if (hasMap) {
        mapEl = h('div', { id: 'profile-map', class: 'profile-map' });
        mapBlock.append(h('div', { class: 'profile-map-wrap' }, mapEl));
        if (edit) {
          mapBlock.append(h('p', { class: 'tiny muted profile-map-hint' }, 'Сейчас показана OpenStreetMap. Виджет 2ГИС ниже заменит её на профиле.'));
        }
      } else if (edit) {
        mapBlock.append(
          h('button', { class: 'profile-placeholder card', type: 'button', onclick: () => editDgisSheet() }, 'Укажите ссылку 2ГИС для запасной карты'),
        );
      }
      if (edit) mapBlock.append(buildInlineMapEditor());
      const actions = h('div', { class: 'profile-map-actions' });
      if (data.dgis_url) {
        actions.append(h('a', { class: 'btn sm', href: data.dgis_url, target: '_blank', rel: 'noopener' }, 'Открыть в 2ГИС'));
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

    body.replaceChildren(heroSection, ...sections);
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