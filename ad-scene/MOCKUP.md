# HTML-макет рекламы (без React)

Белый экран при `python3 -m http.server` из папки `ad-scene` — это **нормально**: в корне лежит `index.html` от Vite, браузер пытается загрузить `/src/main.tsx` и не может его выполнить.

## Правильный запуск макета

```bash
cd ad-scene
python3 serve-mockup.py
```

Открыть: **http://127.0.0.1:8765/index.html**

Или вручную:

```bash
cd ad-scene/mockup
python3 -m http.server 8765
```

## React / Three (если нужна сцена)

```bash
cd ad-scene
npm install
npm run dev
```