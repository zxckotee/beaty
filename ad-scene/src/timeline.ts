import { STORY, TOTAL_STORY_MS, WIDGETS, type WidgetDef } from "./story";

export const CROSSFADE_MS = 900;
export const TARGET_FPS = 24;

export const BEAT_STARTS = STORY.reduce<number[]>((acc, _b, i) => {
  acc.push(i === 0 ? 0 : acc[i - 1] + STORY[i - 1].durationMs);
  return acc;
}, []);

export function smoothstep(edge0: number, edge1: number, x: number) {
  const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

export function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

export function loopedTime(ms: number) {
  return ms % TOTAL_STORY_MS;
}

/** Плавная огибающая акцента виджета 0..1 (без порога «слайда») */
export function widgetEmphasis(widgetIndex: number, ms: number, manualPop: Set<number>): number {
  if (manualPop.has(widgetIndex)) return 1;

  const t = loopedTime(ms);
  const breathe = 0.06 + 0.035 * Math.sin(t * 0.0022 + widgetIndex * 0.7);

  let accent = 0;
  for (let b = 0; b < STORY.length; b++) {
    if (!STORY[b].activeSegments.includes(widgetIndex)) continue;
    const start = BEAT_STARTS[b];
    const end = start + STORY[b].durationMs;
    const enter = smoothstep(start, start + CROSSFADE_MS, t);
    const exit = 1 - smoothstep(end - CROSSFADE_MS, end, t);
    const envelope = enter * exit;
    if (envelope <= 0) continue;

    const local = clamp((t - start) / STORY[b].durationMs, 0, 1);
    const pulse = 0.35 + 0.65 * (0.5 - 0.5 * Math.cos(local * Math.PI * 2));
    accent = Math.max(accent, envelope * pulse);
  }

  return clamp(breathe + accent * 0.92, 0, 1);
}

const SOLUTION_LAYOUT: Partial<Record<number, { x: number; y: number }>> = {
  6: { x: -1.12, y: -0.88 },
  7: { x: 0, y: -0.88 },
  8: { x: 1.12, y: -0.88 },
};

/** Плавный сдвиг карточек решения вместо скачка на бите */
export function layoutAtTime(ms: number): WidgetDef[] {
  const t = loopedTime(ms);
  const solutionStart = BEAT_STARTS[4];
  const blendStart = solutionStart - CROSSFADE_MS;
  const blend = smoothstep(blendStart, solutionStart + CROSSFADE_MS, t);

  return WIDGETS.map((w, i) => {
    const target = SOLUTION_LAYOUT[i];
    if (!target) return w;
    return {
      ...w,
      x: w.x + (target.x - w.x) * blend,
      y: w.y + (target.y - w.y) * blend,
    };
  });
}

export type OverlayBlend = {
  from: number;
  to: number;
  mix: number;
};

/** Плавная смена заголовков поверх сцены */
export function overlayBlend(ms: number): OverlayBlend {
  const t = loopedTime(ms);
  for (let b = 0; b < STORY.length; b++) {
    const start = BEAT_STARTS[b];
    const end = b === STORY.length - 1 ? TOTAL_STORY_MS : BEAT_STARTS[b + 1];
    if (t >= start && t < end) {
      const fadeOutStart = end - CROSSFADE_MS;
      if (t < fadeOutStart) return { from: b, to: b, mix: 0 };
      const mix = smoothstep(fadeOutStart, end, t);
      const to = (b + 1) % STORY.length;
      return { from: b, to, mix };
    }
  }
  return { from: 0, to: 0, mix: 0 };
}

export function screenTilt(ms: number): number {
  const t = loopedTime(ms) * 0.001;
  return 0.05 * Math.sin(t * 0.9) + 0.03 * Math.sin(t * 1.7 + 0.5);
}