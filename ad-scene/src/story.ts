export type StoryBeat = {
  id: string;
  label: string;
  title: string;
  subtitle: string;
  durationMs: number;
  /** Grid column 0–cols-1 */
  activeSegments: number[];
  mood: "hook" | "maps" | "fork" | "pain" | "solution" | "cta";
};

export const SEGMENT_COPY: { title: string; line: string }[] = [
  { title: "Beaty", line: "Клиент уже в Картах" },
  { title: "Яндекс.Карты", line: "Отзывы → контакты" },
  { title: "Телефон", line: "Линия занята → слив" },
  { title: "Ваш бот", line: "Запись за 30 сек" },
  { title: "Пустой слот", line: "Кресло простаивает" },
  { title: "Неявки", line: "Утром дырка" },
  { title: "24/7", line: "Запись вне смены" },
  { title: "Подтверждение", line: "Меньше неявок" },
  { title: "Пора снова", line: "Ритм визитов" },
  { title: "Старт", line: "5 мин · тест бесплатно" },
];

export const STORY: StoryBeat[] = [
  {
    id: "hook",
    label: "Открытие",
    title: "Клиент уже выбрал вас в Картах",
    subtitle: "На последнем шаге вы забираете деньги — или дарите их соседу",
    durationMs: 4000,
    activeSegments: [0],
    mood: "hook",
  },
  {
    id: "maps",
    label: "Путь",
    title: "Карты → контакты",
    subtitle: "Человек рядом, рейтинг, кнопка «Записаться» в Telegram",
    durationMs: 5000,
    activeSegments: [0, 1],
    mood: "maps",
  },
  {
    id: "fork",
    label: "Развилка",
    title: "Один тап — два исхода",
    subtitle: "Только телефон сливает трафик. Ваш бот закрывает в кассе",
    durationMs: 5500,
    activeSegments: [2, 3],
    mood: "fork",
  },
  {
    id: "pain",
    label: "Боль",
    title: "Дыры в выручке",
    subtitle: "Простой, неявки, WhatsApp ночью, потерянный ритм",
    durationMs: 5000,
    activeSegments: [4, 5],
    mood: "pain",
  },
  {
    id: "solution",
    label: "Три удара",
    title: "Ваш бренд в Telegram",
    subtitle: "Не витрина конкурентов — своя запись под вашим именем",
    durationMs: 6000,
    activeSegments: [6, 7, 8],
    mood: "solution",
  },
  {
    id: "cta",
    label: "CTA",
    title: "Карты приводят — бот закрывает",
    subtitle: "Ссылка в Карты, Instagram, ресепшен · 10 минут на демо",
    durationMs: 5000,
    activeSegments: [9],
    mood: "cta",
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