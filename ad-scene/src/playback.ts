import { createContext, useContext } from "react";

export type PlaybackState = {
  timeMs: number;
  playing: boolean;
  popped: Set<number>;
};

export const defaultPlayback: PlaybackState = {
  timeMs: 0,
  playing: true,
  popped: new Set(),
};

export const PlaybackContext = createContext<{
  state: PlaybackState;
  setPlaying: (v: boolean) => void;
  togglePop: (i: number) => void;
  restart: () => void;
  /** Для оверлея React — синхронизация ~24 Гц */
  syncUi: (ms: number) => void;
} | null>(null);

export function usePlayback() {
  const ctx = useContext(PlaybackContext);
  if (!ctx) throw new Error("PlaybackContext");
  return ctx;
}