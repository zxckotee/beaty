import type { WidgetKind } from "./uiTokens";

export type StoryBeat = {
  id: string;
  label: string;
  title: string;
  subtitle: string;
  durationMs: number;
  /** Какие виджеты «вылетают» на этом бите */
  activeSegments: number[];
};

export type WidgetDef = {
  title: string;
  line: string;
  kind: WidgetKind;
  x: number;
  y: number;
  w: number;
  h: number;
};

/** Раскладка как блоки на экране приложения (центр — 0,0) */
export const WIDGETS: WidgetDef[] = [
  { title: "Beaty-Welcome", line: "Запись под вашим брендом", kind: "soft", x: 0, y: 2.05, w: 3.4, h: 0.52 },
  { title: "Яндекс.Карты", line: "Клиент уже нашёл вас", kind: "card", x: 0, y: 1.35, w: 3.4, h: 0.58 },
  { title: "Позвонить", line: "Линия занята · вечер", kind: "ghost", x: -0.82, y: 0.55, w: 1.55, h: 0.48 },
  { title: "Записаться", line: "Telegram · ваш бот", kind: "primary", x: 0.82, y: 0.55, w: 1.55, h: 0.48 },
  { title: "Пустой слот", line: "Мастер ждёт", kind: "chip-warn", x: -0.9, y: -0.15, w: 1.5, h: 0.38 },
  { title: "Неявка", line: "Утром дырка", kind: "chip-bad", x: 0.9, y: -0.15, w: 1.5, h: 0.38 },
  { title: "24/7", line: "Запись вне смены", kind: "soft", x: 0, y: -0.85, w: 1.05, h: 0.42 },
  { title: "Подтвердить", line: "Меньше неявок", kind: "soft", x: 0, y: -0.85, w: 1.05, h: 0.42 },
  { title: "Пора снова", line: "Ритм визитов", kind: "soft", x: 0, y: -0.85, w: 1.05, h: 0.42 },
  { title: "Подключить тест", line: "5 минут · демо", kind: "primary", x: 0, y: -1.55, w: 2.8, h: 0.52 },
];

export const STORY: StoryBeat[] = [
  {
    id: "hook",
    label: "Открытие",
    title: "Клиент уже выбрал вас в Картах",
    subtitle: "Последний шаг — вы забираете запись или отдаёте её соседу",
    durationMs: 4000,
    activeSegments: [0],
  },
  {
    id: "maps",
    label: "Путь",
    title: "Карты → контакты",
    subtitle: "Рейтинг, адрес, кнопка записи",
    durationMs: 4800,
    activeSegments: [1],
  },
  {
    id: "fork",
    label: "Развилка",
    title: "Телефон или бот",
    subtitle: "Звонок сливает трафик. Кнопка Telegram закрывает сделку",
    durationMs: 5200,
    activeSegments: [2, 3],
  },
  {
    id: "pain",
    label: "Боль",
    title: "Простой и неявки",
    subtitle: "То, что бьёт по выручке каждый день",
    durationMs: 4800,
    activeSegments: [4, 5],
  },
  {
    id: "solution",
    label: "Решение",
    title: "Три результата Beaty-Welcome",
    subtitle: "24/7, подтверждения, возвраты по ритму",
    durationMs: 5800,
    activeSegments: [6, 7, 8],
  },
  {
    id: "cta",
    label: "CTA",
    title: "Карты приводят — бот закрывает",
    subtitle: "Ссылка в Карты и QR на ресепшен",
    durationMs: 5000,
    activeSegments: [9],
  },
];

export const TOTAL_STORY_MS = STORY.reduce((s, b) => s + b.durationMs, 0);

export function beatAt(elapsed: number): { index: number; local: number } {
  const t = elapsed % TOTAL_STORY_MS;
  let acc = 0;
  for (let i = 0; i < STORY.length; i++) {
    const d = STORY[i].durationMs;
    if (t < acc + d) return { index: i, local: (t - acc) / d };
    acc += d;
  }
  return { index: 0, local: 0 };
}

/** Три карточки решения — по горизонтали на бите solution */
export function widgetLayoutForBeat(beatIndex: number): WidgetDef[] {
  if (beatIndex !== 4) return WIDGETS;
  return WIDGETS.map((w, i) => {
    if (i === 6) return { ...w, x: -1.12, y: -0.88 };
    if (i === 7) return { ...w, x: 0, y: -0.88 };
    if (i === 8) return { ...w, x: 1.12, y: -0.88 };
    return w;
  });
}