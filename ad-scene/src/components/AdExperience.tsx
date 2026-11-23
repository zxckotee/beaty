import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, PerspectiveCamera, Stars } from "@react-three/drei";
import * as THREE from "three";
import { STORY, SEGMENT_COPY, beatAt } from "../story";
import { HolographicPlane } from "./HolographicPlane";
import { PopSegment } from "./PopSegment";

const PLANE_W = 7.2;
const PLANE_H = 4.8;
const COLS = 5;
const ROWS = 2;

function moodAccent(mood: string): [number, number, number] {
  const map: Record<string, [number, number, number]> = {
    hook: [0.55, 0.35, 1],
    maps: [0.2, 0.75, 1],
    fork: [0.3, 0.9, 0.7],
    pain: [1, 0.25, 0.35],
    solution: [0.2, 1, 0.55],
    cta: [1, 0.85, 0.2],
  };
  return map[mood] ?? [0.6, 0.4, 1];
}

function CameraRig({ beatIndex }: { beatIndex: number }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3(0, 0.2, 6.8));

  useFrame((state, delta) => {
    const beat = beatIndex / STORY.length;
    const parallaxX = Math.sin(state.clock.elapsedTime * 0.35) * 0.35;
    const parallaxY = 0.25 + beat * 0.15 + Math.cos(state.clock.elapsedTime * 0.28) * 0.1;
    target.current.set(parallaxX, parallaxY, 6.8 - beat * 0.4);
    camera.position.lerp(target.current, 1 - Math.exp(-4 * delta));
    camera.lookAt(0, 0, 0);
  });

  return <PerspectiveCamera makeDefault position={[0, 0.3, 7]} fov={42} />;
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
  const screenRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!screenRef.current) return;
    const autoSpin = state.clock.elapsedTime * 0.15;
    screenRef.current.rotation.y = Math.sin(autoSpin) * 0.55 + local * 0.2;
    screenRef.current.rotation.x = Math.cos(autoSpin * 0.7) * 0.12;
  });

  const segments = useMemo(() => {
    return SEGMENT_COPY.map((copy, i) => {
      const col = i % COLS;
      const row = Math.floor(i / COLS);
      const active = beat.activeSegments.includes(i);
      const pop = popped.has(i) || (active && local > 0.55);
      const accent = moodAccent(beat.mood);
      return (
        <PopSegment
          key={copy.title}
          index={i}
          col={col}
          row={row}
          cols={COLS}
          rows={ROWS}
          width={PLANE_W}
          height={PLANE_H}
          title={copy.title}
          line={copy.line}
          active={active}
          pop={pop}
          accent={accent}
          onClick={onPop}
        />
      );
    });
  }, [beat, local, onPop, popped]);

  return (
    <>
      <CameraRig beatIndex={beatIndex} />
      <ambientLight intensity={0.35} />
      <directionalLight
        position={[4, 6, 5]}
        intensity={1.4}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <pointLight position={[-5, 2, 3]} intensity={2.2} color="#7b5cff" />
      <pointLight position={[5, -1, 2]} intensity={1.6} color="#22d3ff" />
      <Float speed={1.2} rotationIntensity={0.15} floatIntensity={0.25}>
        <group ref={screenRef}>
          <HolographicPlane width={PLANE_W} height={PLANE_H} mood={beat.mood} tilt={local} />
          <group position={[0, 0, 0.06]}>{segments}</group>
        </group>
      </Float>
      <Stars radius={80} depth={40} count={1200} factor={3} saturation={0.6} fade speed={0.6} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.2, 0]} receiveShadow>
        <planeGeometry args={[30, 30]} />
        <meshStandardMaterial color="#0a0614" metalness={0.6} roughness={0.4} />
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
      <div className="ad-overlay">
        <div className="ad-brand">Beaty</div>
        <h1 className="ad-title">{beat.title}</h1>
        <p className="ad-sub">{beat.subtitle}</p>
        <div className="ad-controls">
          <button
            type="button"
            onClick={() => {
              if (playing) {
                pausedAt.current = elapsed;
                startRef.current = null;
                setPlaying(false);
              } else {
                setPlaying(true);
              }
            }}
          >
            {playing ? "Пауза" : "Играть"}
          </button>
          <button
            type="button"
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
        <p className="ad-hint">Нажмите на сегмент — он выйдет из плоскости с пружиной</p>
      </div>
      <Canvas shadows gl={{ antialias: true, alpha: true }} dpr={[1, 2]}>
        <color attach="background" args={["#05020c"]} />
        <fog attach="fog" args={["#05020c", 8, 22]} />
        <SceneContent beatIndex={beatIndex} local={local} popped={popped} onPop={onPop} />
      </Canvas>
    </div>
  );
}