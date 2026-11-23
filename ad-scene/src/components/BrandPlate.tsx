import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useTexture } from "@react-three/drei";
import type { Group } from "three";
import * as THREE from "three";
import type { PlaybackState } from "../playback";

export function BrandPlate({ playbackRef }: { playbackRef: React.MutableRefObject<PlaybackState> }) {
  const ref = useRef<Group>(null);
  const tex = useTexture("/beaty-welcome-hero.png");

  useFrame((_, delta) => {
    if (!ref.current) return;
    const ms = playbackRef.current.timeMs;
    const t = ms * 0.001;
    const k = 1 - Math.exp(-8 * delta);
    const targetY = Math.sin(t * 0.8) * 0.04;
    const targetRy = Math.sin(t * 0.35) * 0.08;
    ref.current.position.y += (targetY - ref.current.position.y) * k;
    ref.current.rotation.y += (0.12 + targetRy - ref.current.rotation.y) * k;

    const mesh = ref.current.children[0] as THREE.Mesh;
    const mat = mesh.material as THREE.MeshStandardMaterial;
    const targetGlow = 0.14 + Math.sin(t * 1.2) * 0.05;
    mat.emissiveIntensity += (targetGlow - mat.emissiveIntensity) * k;
  });

  return (
    <group ref={ref} position={[-2.55, 0.1, 0.1]}>
      <mesh>
        <planeGeometry args={[2.15, 2.15]} />
        <meshStandardMaterial
          map={tex}
          toneMapped
          metalness={0.15}
          roughness={0.55}
          emissive="#B8A06A"
          emissiveIntensity={0.14}
          transparent
        />
      </mesh>
    </group>
  );
}