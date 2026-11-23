/** Синхрон с backend/app/web/static/css/app.css */
export const UI = {
  gold: "#B8A06A",
  goldDeep: "#948256",
  bg: "#000000",
  surface: "#141414",
  surface2: "#1a1a1a",
  text: "#ececec",
  muted: "#a3a3a3",
  line: "#2a2a2a",
  accentInk: "#1a1a1a",
  ok: "#3ccf93",
  warn: "#f0a844",
  bad: "#ff6f87",
  radius: 0.22,
  radiusSm: 0.14,
} as const;

export type WidgetKind = "primary" | "ghost" | "card" | "chip-warn" | "chip-bad" | "soft";