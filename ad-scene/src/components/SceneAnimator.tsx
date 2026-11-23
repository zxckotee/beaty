import { useRef, type MutableRefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { PerspectiveCamera } from "@react-three/drei";
import type { Group } from "three";
import { WIDGETS } from "../story";
import { loopedTime } from "../timeline";
import type { PlaybackState } from "../playback";
import { ScreenPanel } from "./ScreenPanel";
import { UiWidget3d } from "./UiWidget3d";
import { BrandPlate } from "./BrandPlate";
import { UI } from "../uiTokens";

const PLANE_W = 3.6;
const PLANE_H = 5.2;

type Props = {
  playbackRef: MutableRefObject<PlaybackState>;
  onPop: (i: number) => void;
  syncUi: (ms: number) => void;
};

export function SceneAnimator({ playbackRef, onPop, syncUi }: Props) {
  const screenRef = useRef<Group>(null);
  const camPos = useRef({ x: 0, y: 0.15, z: 5.4 });
  const uiAccum = useRef(0);
  const { camera } = useThree();

  useFrame((_state, delta) => {
    const pb = playbackRef.current;
    if (pb.playing) {
      pb.timeMs += delta * 1000;
    }

    const t = loopedTime(pb.timeMs);

    uiAccum.current += delta;
    if (uiAccum.current >= 1 / 24) {
      uiAccum.current = 0;
      syncUi(pb.timeMs);
    }

    if (screenRef.current) {
      const k = 1 - Math.exp(-8 * delta);
      const targetRy = -0.2 + Math.sin(t * 0.001 * 0.9) * 0.04;
      screenRef.current.rotation.y += (targetRy - screenRef.current.rotation.y) * k;
    }

    const targetX = Math.sin(t * 0.00035) * 0.08;
    const targetY = 0.15 + Math.sin(t * 0.00045) * 0.04;
    const k = 1 - Math.exp(-6 * delta);
    camPos.current.x += (targetX - camPos.current.x) * k;
    camPos.current.y += (targetY - camPos.current.y) * k;
    camera.position.set(camPos.current.x, camPos.current.y, camPos.current.z);
    camera.lookAt(0, 0, 0);
  });

  return (
    <>
      <color attach="background" args={[UI.bg]} />
      <fog attach="fog" args={[UI.bg, 8, 18]} />
      <PerspectiveCamera makeDefault position={[0, 0.15, 5.4]} fov={38} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[3, 5, 4]} intensity={0.85} castShadow color="#fffef8" />
      <directionalLight position={[-4, 1, 2]} intensity={0.35} color={UI.gold} />
      <BrandPlate playbackRef={playbackRef} />
      <group ref={screenRef}>
        <ScreenPanel width={PLANE_W} height={PLANE_H} playbackRef={playbackRef} />
        <group position={[0, 0, 0.05]}>
          {WIDGETS.map((def, i) => (
            <UiWidget3d key={def.title} index={i} def={def} playbackRef={playbackRef} onClick={onPop} />
          ))}
        </group>
      </group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -3.2, 0]} receiveShadow>
        <planeGeometry args={[12, 12]} />
        <meshStandardMaterial color={UI.bg} metalness={0.2} roughness={0.95} />
      </mesh>
    </>
  );
}