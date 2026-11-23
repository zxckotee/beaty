import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox } from "@react-three/drei";
import * as THREE from "three";
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
  tilt: number;
};

/** Плоскость «экрана» продукта — без шейдеров, как карточка в админке */
export function ScreenPanel({ width, height, tilt }: Props) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!groupRef.current) return;
    groupRef.current.rotation.x = 0.06 + tilt * 0.04;
    groupRef.current.rotation.y = -0.22 + Math.sin(state.clock.elapsedTime * 0.15) * 0.03;
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