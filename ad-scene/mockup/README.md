# HTML-макет рекламы Beaty-Welcome

Статичная вёрстка всех плашек для последующей анимации в других инструментах.

```bash
cd ad-scene
python3 serve-mockup.py
```

Или:

```bash
cd ad-scene/mockup
python3 -m http.server 8765
```

Открыть [http://127.0.0.1:8765/index.html](http://127.0.0.1:8765/index.html)

Не запускайте `http.server` из корня `ad-scene/` — там Vite `index.html`, будет белый экран.

## Файлы

- `index.html` — мастер-кадр + 6 beat-кадров + каталог компонентов
- `ad-ui.css` — токены как `backend/app/web/static/css/app.css`
- Логотип: `../public/beaty-welcome-hero.png`

## ID плашек (master)

| id | Сюжет |
|----|--------|
| `plate-00-beaty-welcome` | hook |
| `plate-01-maps` | maps |
| `plate-02-phone`, `plate-03-bot` | fork |
| `plate-04-empty-slot`, `plate-05-noshow` | pain |
| `plate-06-247`, `plate-07-confirm`, `plate-08-rhythm` | solution |
| `plate-09-cta` | cta |