import { Suspense, useCallback, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { PlaybackContext, type PlaybackState } from "../playback";
import { SceneAnimator } from "./SceneAnimator";
import { NarrativeOverlay } from "./NarrativeOverlay";

export function AdExperience() {
  const playbackRef = useRef<PlaybackState>({
    timeMs: 0,
    playing: true,
    popped: new Set(),
  });
  const [uiTimeMs, setUiTimeMs] = useState(0);
  const [playingUi, setPlayingUi] = useState(true);

  const syncUi = useCallback((ms: number) => {
    setUiTimeMs(ms);
  }, []);

  const setPlaying = useCallback((playing: boolean) => {
    playbackRef.current.playing = playing;
    setPlayingUi(playing);
    setUiTimeMs(playbackRef.current.timeMs);
  }, []);

  const togglePop = useCallback((i: number) => {
    const next = new Set(playbackRef.current.popped);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    playbackRef.current.popped = next;
    playbackRef.current.playing = false;
    setPlayingUi(false);
    setUiTimeMs(playbackRef.current.timeMs);
  }, []);

  const restart = useCallback(() => {
    playbackRef.current.timeMs = 0;
    playbackRef.current.popped = new Set();
    playbackRef.current.playing = true;
    setPlayingUi(true);
    setUiTimeMs(0);
  }, []);

  const ctx = useMemo(
    () => ({ state: playbackRef.current, setPlaying, togglePop, restart, syncUi }),
    [restart, setPlaying, syncUi, togglePop],
  );

  return (
    <PlaybackContext.Provider value={ctx}>
      <div className="ad-root">
        <NarrativeOverlay timeMs={uiTimeMs} />
        <div className="ad-controls-bar">
          <button type="button" className="btn primary" onClick={() => setPlaying(!playingUi)}>
            {playingUi ? "Пауза" : "Играть"}
          </button>
          <button type="button" className="btn ghost" onClick={restart}>
            Сначала
          </button>
          <span className="ad-hint-inline">24 fps · плавный таймлайн · клик — зафиксировать виджет</span>
        </div>
        <Canvas shadows dpr={[1, 2]} gl={{ antialias: true }} frameloop="always">
          <Suspense fallback={null}>
            <SceneAnimator playbackRef={playbackRef} onPop={togglePop} syncUi={syncUi} />
          </Suspense>
        </Canvas>
      </div>
    </PlaybackContext.Provider>
  );
}