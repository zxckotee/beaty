# Beaty — holographic ad scene

3D-реклама по сценарию `docs/sales-call-script.md`: автопроигрывание, интерактивные сегменты, iridescent-плоскость.

## Запуск

```bash
cd ad-scene
npm install
npm run dev
```

Откройте URL Vite (обычно `http://127.0.0.1:5173`).

## Стек

- **React Three Fiber** + **Three.js** — сцена, камера, тени
- **@react-three/drei** — текст, звёзды, float
- **@react-spring/three** — пружинный выход сегментов по клику

## Устройство

1. **Плоскость-экран** (`HolographicPlane`) — subdivided mesh, vertex shader (wave/ripple), fragment shader (iridescent).
2. **Сетка 5×2** (`PopSegment`) — клик «продавливает» сегмент по Z с spring-анимацией.
3. **Камера** — параллакс и приближение по ходу сюжета.
4. **Сюжет** (`story.ts`) — 6 битов: крючок → Карты → развилка → боль → три удара → CTA.