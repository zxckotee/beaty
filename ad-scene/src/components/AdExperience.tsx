import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { PerspectiveCamera } from "@react-three/drei";
import { STORY, beatAt, widgetLayoutForBeat } from "../story";
import { ScreenPanel } from "./ScreenPanel";
import { UiWidget3d } from "./UiWidget3d";
import { UI } from "../uiTokens";

const PLANE_W = 3.6;
const PLANE_H = 5.2;

function CameraRig() {
  const { camera } = useThree();

  useEffect(() => {
    camera.near = 0.1;
    camera.far = 50;
    camera.updateProjectionMatrix();
  }, [camera]);

  return (
    <PerspectiveCamera makeDefault position={[0, 0.15, 5.4]} fov={38} />
  );
}

function SceneContent({
  beatIndex,
  local,
  popped,
  onPop,
}: {
  beatIndex: number;
  local: number;
  popped: Set<number>;
  onPop: (i: number) => void;
}) {
  const beat = STORY[beatIndex];
  const layout = widgetLayoutForBeat(beatIndex);

  const widgets = useMemo(() => {
    return layout.map((def, i) => {
      const active = beat.activeSegments.includes(i);
      const pop = popped.has(i) || (active && local > 0.45);
      return (
        <UiWidget3d key={`${def.title}-${i}`} index={i} def={def} active={active} pop={pop} onClick={onPop} />
      );
    });
  }, [beat, layout, local, onPop, popped]);

  return (
    <>
      <color attach="background" args={[UI.bg]} />
      <fog attach="fog" args={[UI.bg, 7, 16]} />
      <CameraRig />
      <ambientLight intensity={0.55} />
      <directionalLight position={[3, 5, 4]} intensity={0.85} castShadow color="#fffef8" />
      <directionalLight position={[-4, 1, 2]} intensity={0.25} color={UI.gold} />
      <group position={[0, 0, 0]}>
        <ScreenPanel width={PLANE_W} height={PLANE_H} tilt={local} />
        <group position={[0, 0, 0.05]}>{widgets}</group>
      </group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -3.2, 0]} receiveShadow>
        <planeGeometry args={[12, 12]} />
        <meshStandardMaterial color={UI.bg} metalness={0.2} roughness={0.95} />
      </mesh>
    </>
  );
}

export function AdExperience() {
  const [playing, setPlaying] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const [popped, setPopped] = useState<Set<number>>(() => new Set());
  const startRef = useRef<number | null>(null);
  const pausedAt = useRef(0);

  const onPop = useCallback((index: number) => {
    setPopped((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
    setPlaying(false);
    pausedAt.current = elapsed;
    startRef.current = null;
  }, [elapsed]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = (now: number) => {
      if (startRef.current === null) startRef.current = now - pausedAt.current;
      setElapsed(now - startRef.current);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const { index: beatIndex, local } = beatAt(elapsed);
  const beat = STORY[beatIndex];

  useEffect(() => {
    setPopped(new Set());
  }, [beatIndex]);

  return (
    <div className="ad-root">
      <div className="ad-chrome">
        <p className="ad-brand">Beaty</p>
        <h1 className="ad-title">{beat.title}</h1>
        <p className="ad-sub">{beat.subtitle}</p>
        <div className="ad-controls">
          <button
            type="button"
            className="btn primary"
            onClick={() => {
              if (playing) {
                pausedAt.current = elapsed;
                startRef.current = null;
                setPlaying(false);
              } else setPlaying(true);
            }}
          >
            {playing ? "Пауза" : "Играть"}
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              pausedAt.current = 0;
              startRef.current = null;
              setElapsed(0);
              setPopped(new Set());
              setPlaying(true);
            }}
          >
            Сначала
          </button>
          <span className="ad-beat">{beat.label}</span>
        </div>
        <p className="ad-hint">Клик по кнопке на экране — она вылетает из плоскости</p>
      </div>
      <Canvas shadows dpr={[1, 2]} gl={{ antialias: true }}>
        <SceneContent beatIndex={beatIndex} local={local} popped={popped} onPop={onPop} />
      </Canvas>
    </div>
  );
}