import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox } from "@react-three/drei";
import type { Group } from "three";
import * as THREE from "three";
import { screenTilt } from "../timeline";
import type { PlaybackState } from "../playback";
import { UI } from "../uiTokens";

const screenMat = new THREE.MeshStandardMaterial({
  color: UI.surface,
  metalness: 0.05,
  roughness: 0.92,
});

const bezelMat = new THREE.MeshStandardMaterial({
  color: UI.surface2,
  metalness: 0.1,
  roughness: 0.88,
});

type Props = {
  width: number;
  height: number;
  playbackRef: React.MutableRefObject<PlaybackState>;
};

export function ScreenPanel({ width, height, playbackRef }: Props) {
  const groupRef = useRef<Group>(null);

  useFrame(() => {
    if (!groupRef.current) return;
    const tilt = screenTilt(playbackRef.current.timeMs);
    groupRef.current.rotation.x = 0.06 + tilt;
  });

  return (
    <group ref={groupRef}>
      <RoundedBox args={[width + 0.12, height + 0.12, 0.06]} radius={UI.radius} smoothness={4} material={bezelMat} />
      <mesh position={[0, 0, 0.04]} material={screenMat}>
        <planeGeometry args={[width, height]} />
      </mesh>
    </group>
  );
}